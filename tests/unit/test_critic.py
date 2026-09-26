"""Tests for critic.py's routing logic (T086) — the deterministic part
(`route_action`) plus the US3 additions: AssertionViolated/
AssertionNotEvaluable routing and the two-consecutive-occurrence rule
(`_is_repeated_not_evaluable`). See plan.md's "Roteamento do critic" table
and data-model.md's closed error taxonomy.
"""

from pathlib import Path

import pytest

from qcagent.llm.base import BaseLLMClient, LLMResponse
from qcagent.nodes.critic import (
    _is_repeated_not_evaluable,
    make_critic_node,
    route_action,
)
from qcagent.state import (
    AssertionOutcome,
    ErrorRecord,
    GateRestrictionAssertion,
    MeasuresAssertion,
    ResourceResult,
    SemanticResult,
    StaticResult,
)


class ScriptedLLMClient(BaseLLMClient):
    model_id = "scripted-fake"

    def __init__(self, responses: list[str], cache_dir: Path) -> None:
        self.responses = responses
        self.calls = 0
        self.cache_dir = cache_dir

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        text = self.responses[self.calls]
        self.calls += 1
        return LLMResponse(
            text=text,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_s=0.001,
            model_id=self.model_id,
        )


def _measures(qubits: list[int] | None, expected: str) -> MeasuresAssertion:
    return MeasuresAssertion(qubits=qubits, expected=expected)


def _outcome(assertion, passed: bool | None, detail: str = "") -> AssertionOutcome:
    return AssertionOutcome(assertion=assertion, passed=passed, detail=detail)


def _not_evaluable_error(iteration: int, assertion) -> ErrorRecord:
    return ErrorRecord(
        iteration=iteration,
        stage="semantic",
        error_type="AssertionNotEvaluable",
        message="not evaluable",
        payload={"assertion": assertion.model_dump(mode="json")},
    )


# ---------------------------------------------------------------------------
# Pre-existing routing behavior (regression coverage — this file is new)
# ---------------------------------------------------------------------------


def test_done_when_nothing_failed() -> None:
    action, error_type = route_action(None, None, None, None, 0, 5, [])
    assert action == "done"
    assert error_type is None


def test_static_error_routes_to_retry_generation() -> None:
    static = StaticResult(
        parsed=True,
        executed=False,
        transpiled=False,
        error=ErrorRecord(iteration=0, stage="static", error_type="SyntaxError", message="x"),
    )
    action, error_type = route_action(static, None, None, None, 0, 5, [])
    assert action == "retry_generation"
    assert error_type == "SyntaxError"


def test_resource_excess_routes_to_optimize() -> None:
    resource = ResourceResult(
        depth=10, cx_count=5, width=2, depth_ratio=3.0, cx_ratio=1.0, passed=False
    )
    action, error_type = route_action(None, None, None, resource, 0, 5, [])
    assert action == "optimize"
    assert error_type == "ResourceExcess"


def test_max_iter_exhausted_aborts() -> None:
    static = StaticResult(
        parsed=True,
        executed=False,
        transpiled=False,
        error=ErrorRecord(iteration=5, stage="static", error_type="SyntaxError", message="x"),
    )
    action, error_type = route_action(static, None, None, None, 5, 5, [])
    assert action == "abort"
    assert error_type == "SyntaxError"


def test_unroutable_error_type_raises() -> None:
    semantic = SemanticResult(
        passed=False,
        error=ErrorRecord(iteration=0, stage="semantic", error_type="NotARealType", message="x"),
    )
    with pytest.raises(ValueError, match="unroutable error_type"):
        route_action(None, None, semantic, None, 0, 5, [])


# ---------------------------------------------------------------------------
# US3 — AssertionViolated / AssertionNotEvaluable routing
# ---------------------------------------------------------------------------


def test_assertion_violated_routes_to_retry_generation() -> None:
    outcomes = [_outcome(_measures(None, "00"), False, "got 0.5")]
    action, error_type = route_action(None, outcomes, None, None, 0, 5, [])
    assert action == "retry_generation"
    assert error_type == "AssertionViolated"


def test_empty_assertion_results_is_not_a_failure() -> None:
    """`assertion_check` returns [] when no assertions were declared — that
    must fall through to the next layer, never be treated as a violation."""
    action, error_type = route_action(None, [], None, None, 0, 5, [])
    assert action == "done"
    assert error_type is None


def test_violation_takes_priority_over_not_evaluable_in_the_same_iteration() -> None:
    a = _measures(None, "00")
    b = GateRestrictionAssertion(allowed_gates=frozenset({"h"}))
    outcomes = [_outcome(a, None, "not evaluable"), _outcome(b, False, "violated")]
    action, error_type = route_action(None, outcomes, None, None, 0, 5, [])
    assert error_type == "AssertionViolated"


def test_static_error_takes_priority_over_assertion_results() -> None:
    static = StaticResult(
        parsed=True,
        executed=False,
        transpiled=False,
        error=ErrorRecord(iteration=0, stage="static", error_type="SyntaxError", message="x"),
    )
    outcomes = [_outcome(_measures(None, "00"), False, "violated")]
    action, error_type = route_action(static, outcomes, None, None, 0, 5, [])
    assert error_type == "SyntaxError"


def test_first_not_evaluable_occurrence_retries_generation() -> None:
    a = _measures(None, "00")
    outcomes = [_outcome(a, None, "phase undefined")]
    # error_history already contains THIS iteration's record (assertion_check
    # writes it before critic runs), but nothing from a previous iteration.
    error_history = [_not_evaluable_error(0, a)]
    action, error_type = route_action(None, outcomes, None, None, 0, 5, error_history)
    assert action == "retry_generation"
    assert error_type == "AssertionNotEvaluable"


def test_repeated_not_evaluable_aborts_before_max_iter() -> None:
    """The two-consecutive-occurrence rule fires even with budget left
    (iteration=1 < max_iter=5) — regenerating didn't resolve it once, and
    that's the signal to stop, not wait for MAX_ITER."""
    a = _measures(None, "00")
    outcomes = [_outcome(a, None, "phase undefined")]
    error_history = [_not_evaluable_error(0, a), _not_evaluable_error(1, a)]
    action, error_type = route_action(None, outcomes, None, None, 1, 5, error_history)
    assert action == "abort"
    assert error_type == "AssertionNotEvaluable"


def test_different_assertion_not_evaluable_on_consecutive_iters_does_not_trigger_abort() -> None:
    """Regression guard: two DIFFERENT assertions each being not-evaluable
    once, on consecutive iterations, must not be mistaken for the SAME
    assertion recurring."""
    a = _measures(None, "00")
    b = _measures(None, "11")
    outcomes = [_outcome(b, None, "phase undefined")]
    error_history = [_not_evaluable_error(0, a), _not_evaluable_error(1, b)]
    action, error_type = route_action(None, outcomes, None, None, 1, 5, error_history)
    assert action == "retry_generation"
    assert error_type == "AssertionNotEvaluable"


def test_is_repeated_not_evaluable_direct() -> None:
    a = _measures([0, 1], "01")
    assert _is_repeated_not_evaluable([_not_evaluable_error(2, a), _not_evaluable_error(3, a)], 3)
    assert not _is_repeated_not_evaluable([_not_evaluable_error(2, a)], 3)
    assert not _is_repeated_not_evaluable([_not_evaluable_error(3, a)], 3)  # no iteration 2 entry


# ---------------------------------------------------------------------------
# make_critic_node — FR-012 (assertion named in the hint), abort rationale
# ---------------------------------------------------------------------------


def test_critic_node_names_the_violated_assertion_in_the_hint_prompt(tmp_path: Path) -> None:
    llm = ScriptedLLMClient(['{"rationale": "r", "hint": "h"}'], tmp_path / "cache")
    node = make_critic_node(llm, max_iter=5)
    a = _measures(None, "00")
    state = {
        "static": None,
        "assertion_results": [_outcome(a, False, "probability of '00' = 0.2, need >= 0.999999")],
        "semantic": None,
        "resource": None,
        "iteration": 0,
        "error_history": [],
        "code": "qc = ...",
    }
    node(state)
    assert llm.calls == 1

    from qcagent.nodes.critic import _build_hint_prompt

    rendered = _build_hint_prompt("retry_generation", "AssertionViolated", state)
    assert "VIOLATED" in rendered
    assert "probability of '00'" in rendered
    # Named by its own text, not only its kind ("measures") — FR-012.
    assert 'MEASURES == "00"' in rendered


def test_critic_node_abort_rationale_distinguishes_repeat_from_max_iter(tmp_path: Path) -> None:
    llm = ScriptedLLMClient([], tmp_path / "cache")  # never called — abort makes no LLM call
    node = make_critic_node(llm, max_iter=5)
    a = _measures(None, "00")
    state = {
        "static": None,
        "assertion_results": [_outcome(a, None, "phase undefined")],
        "semantic": None,
        "resource": None,
        "iteration": 1,
        "error_history": [_not_evaluable_error(0, a), _not_evaluable_error(1, a)],
        "code": "qc = ...",
    }
    result = node(state)
    assert result["decision"].action == "abort"
    assert "duas tentativas" in result["decision"].rationale
    assert "atingiu MAX_ITER" not in result["decision"].rationale
    assert llm.calls == 0


def test_critic_trace_carries_rationale_and_hints(tmp_path: Path) -> None:
    """F27: the trace is persisted so a failed retry_retrieval can be diagnosed
    afterwards — which needs WHAT the critic asked for, not only the action."""
    llm = ScriptedLLMClient(['{"rationale": "símbolo inventado", "hint": "HGate"}'], tmp_path)
    node = make_critic_node(llm, max_iter=5)
    state = {
        "static": StaticResult(
            parsed=True,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=0,
                stage="static",
                error_type="HallucinatedSymbol",
                message="ImportError: cannot import name 'H' from 'qiskit.circuit.library'",
            ),
        ),
        "assertion_results": [],
        "semantic": None,
        "resource": None,
        "iteration": 0,
        "error_history": [],
        "code": "from qiskit.circuit.library import H",
    }
    (entry,) = node(state)["trace"]
    assert entry["action"] == "retry_retrieval"
    assert entry["rationale"] == "símbolo inventado"
    assert entry["retrieval_hint"] == "HGate"
    assert entry["generation_hint"] is None
