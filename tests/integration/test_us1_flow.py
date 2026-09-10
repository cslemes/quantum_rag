"""T030 — integration test for User Story 1's full graph (T024-T029).

Covers the four acceptance scenarios from spec.md's User Story 1, plus two
properties the task explicitly calls out: an infrastructure failure must
short-circuit before ever reaching the critic, and `interrupt_before` must
default to off.

No live LLM or Qdrant: `ScriptedLLMClient` returns pre-recorded responses
(planner/generator/critic all speak the same `generate()` interface), and
the retriever is a stub that returns no chunks — retrieval itself is Phase 4
(T031-T042), out of scope here. The graph is exercised exactly as
bench/runner.py would use it in production.
"""

import json
from pathlib import Path

import pytest
from qiskit import QuantumCircuit

from qcagent.graph import (
    StatePreparationOracle,
    build_graph,
    make_resource_check_node,
    make_semantic_check_node,
    make_static_check_node,
)
from qcagent.llm.base import BaseLLMClient, LLMResponse, TransientProviderError
from qcagent.nodes.critic import make_critic_node
from qcagent.nodes.generator import make_generator_node
from qcagent.nodes.planner import make_planner_node
from qcagent.state import AgentState
from qcagent.validators.sandbox import WorkerPool

BELL_ORACLE = QuantumCircuit(2)
BELL_ORACLE.h(0)
BELL_ORACLE.cx(0, 1)

VALID_BELL_CODE = (
    "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\n"
)

# Undefined `qc` -> sandbox.py's own RuntimeError -> static.py classifies as
# SyntaxError (its documented fallback for "code that never defines qc").
BROKEN_CODE = "from qiskit import QuantumCircuit\nx = QuantumCircuit(2)\nx.h(0)\n"

# CX is self-inverse (CX^2 = I), so 5 repeats (odd) is unitarily identical to
# one CX — functionally correct, but structurally 5x heavier. At opt_level=0
# (no cancellation pass) this transpiles to depth_ratio=3.0, cx_ratio=5.0
# against BELL_ORACLE, well past the default max_depth_ratio=2.0.
HEAVY_BELL_CODE = (
    "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0)\n" + "qc.cx(0, 1)\n" * 5
)

REQUIREMENTS_JSON = json.dumps(
    {
        "satisfiable": True,
        "rejection_reason": None,
        "requirements": [
            {"id": "r1", "kind": "n_qubits", "description": "2 qubits", "value": 2},
            {"id": "r2", "kind": "property", "description": "produce a Bell state", "value": None},
        ],
    }
)

CRITIC_HINT_JSON = json.dumps({"rationale": "fix and retry", "hint": "try again more carefully"})


class ScriptedLLMClient(BaseLLMClient):
    """Returns one scripted response text per call, in order. Caching is
    disabled (unique cache_dir per instance, never reused) so repeated calls
    in a test always advance instead of hitting a stale cache entry."""

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


class AlwaysTransientLLMClient(BaseLLMClient):
    """Every call raises TransientProviderError — exhausts llm/base.py's
    retry budget and surfaces as InfrastructureError, every time."""

    model_id = "always-down"

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.calls = 0

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        self.calls += 1
        raise TransientProviderError("simulated provider outage")


def _stub_retriever(state: AgentState) -> dict:
    return {"chunks": [], "trace": [{"node": "retriever", "stub": True}]}


def _oracle_loader(_ref: str) -> QuantumCircuit:
    return BELL_ORACLE


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=100) as p:
        yield p


def _build(
    pool: WorkerPool,
    tmp_path: Path,
    *,
    generator_responses: list[str],
    critic_responses: list[str],
    planner_responses: list[str] | None = None,
    max_iter: int = 5,
    resource_opt_level: int = 2,
    interrupt_before: list[str] | None = None,
):
    planner_llm = ScriptedLLMClient(
        planner_responses or [REQUIREMENTS_JSON], tmp_path / "planner_cache"
    )
    generator_llm = ScriptedLLMClient(generator_responses, tmp_path / "generator_cache")
    critic_llm = ScriptedLLMClient(critic_responses, tmp_path / "critic_cache")

    graph = build_graph(
        planner_node=make_planner_node(planner_llm, max_qubits=20),
        retriever_node=_stub_retriever,
        generator_node=make_generator_node(generator_llm),
        static_check_node=make_static_check_node(pool),
        semantic_check_node=make_semantic_check_node(_oracle_loader),
        resource_check_node=make_resource_check_node(_oracle_loader, opt_level=resource_opt_level),
        critic_node=make_critic_node(critic_llm, max_iter=max_iter),
        interrupt_before=interrupt_before,
    )
    return graph, generator_llm, critic_llm


def _initial_state(spec: str = "Build a 2-qubit Bell state") -> AgentState:
    return {
        "task_id": "t-bell",
        "spec": spec,
        "oracle_ref": "bell",
        "coupling_map_name": None,
        "iteration": 0,
    }


# -- Scenario 1: first attempt succeeds --------------------------------------


def test_scenario1_first_attempt_succeeds(pool: WorkerPool, tmp_path: Path) -> None:
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[f"```python\n{VALID_BELL_CODE}```"],
        critic_responses=[],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 1
    assert generator_llm.calls == 1
    assert critic_llm.calls == 0  # "done" needs no LLM hint — see critic.py


# -- Scenario 2: first attempt inexecutable, second attempt fixes it --------


def test_scenario2_regenerates_after_inexecutable_attempt(pool: WorkerPool, tmp_path: Path) -> None:
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[
            f"```python\n{BROKEN_CODE}```",
            f"```python\n{VALID_BELL_CODE}```",
        ],
        critic_responses=[CRITIC_HINT_JSON],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert generator_llm.calls == 2
    generator_trace_entries = [t for t in result["trace"] if t.get("node") == "generator"]
    assert len(generator_trace_entries) == 2  # both attempts recorded
    assert len(result["error_history"]) == 1
    assert result["error_history"][0].error_type == "SyntaxError"


# -- Scenario 3: never succeeds within MAX_ITER ------------------------------


def test_scenario3_reports_explicit_failure_at_max_iter(pool: WorkerPool, tmp_path: Path) -> None:
    max_iter = 2
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[f"```python\n{BROKEN_CODE}```"] * max_iter,
        critic_responses=[CRITIC_HINT_JSON],  # only needed for the retry before the cutoff
        max_iter=max_iter,
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "failed_static"  # never masqueraded as success
    assert result["iteration"] == max_iter
    assert len(result["error_history"]) == max_iter
    assert all(e.error_type == "SyntaxError" for e in result["error_history"])


# -- Scenario 4: correct but resource-heavy -> optimize pass -----------------


def test_scenario4_optimizes_after_resource_excess(pool: WorkerPool, tmp_path: Path) -> None:
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[
            f"```python\n{HEAVY_BELL_CODE}```",
            f"```python\n{VALID_BELL_CODE}```",
        ],
        critic_responses=[CRITIC_HINT_JSON],
        resource_opt_level=0,  # no gate-cancellation pass — see HEAVY_BELL_CODE's comment
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert len(result["error_history"]) == 1
    assert result["error_history"][0].error_type == "ResourceExcess"
    assert result["error_history"][0].stage == "resource"


def test_task_max_depth_ratio_is_actually_used_not_the_hardcoded_default(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Regression test: `TaskSpec.max_depth_ratio` (data-model.md, since
    T043) was defined but never threaded through `make_resource_check_node`
    — every task was silently graded against `check_resources`' own
    hardcoded default (2.0) no matter what its JSON declared (found while
    building T047, research.md D3h). `AgentState["max_depth_ratio"]` now
    carries it the same way `coupling_map_name` already did.

    Same HEAVY_BELL_CODE as `test_scenario4` above (depth_ratio=3.0,
    cx_ratio=5.0 at opt_level=0 against BELL_ORACLE — comfortably over the
    default max_depth_ratio=2.0) but with a state-level `max_depth_ratio`
    loose enough (10.0) to admit it on the FIRST attempt. If the field were
    still ignored (silently falling back to 2.0), this would take 2
    iterations and record a ResourceExcess error, exactly like
    `test_scenario4` — the assertions below only pass if the wiring works.
    """
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[f"```python\n{HEAVY_BELL_CODE}```"],
        critic_responses=[],
        resource_opt_level=0,
    )

    state = _initial_state()
    state["max_depth_ratio"] = 10.0

    result = graph.invoke(state)

    assert result["status"] == "success"
    assert result["iteration"] == 1  # passed on the first attempt, no optimize retry needed
    assert result["error_history"] == []
    assert result["resource"] is not None
    assert result["resource"].passed
    assert result["resource"].depth_ratio > 2.0  # would have failed under the old hardcoded default


# -- Infrastructure failure must short-circuit before the critic ------------


def test_infrastructure_error_never_reaches_critic(pool: WorkerPool, tmp_path: Path) -> None:
    planner_llm = AlwaysTransientLLMClient(tmp_path / "planner_cache")
    generator_llm = ScriptedLLMClient([], tmp_path / "generator_cache")
    critic_calls = {"count": 0}

    def spying_critic(state: AgentState) -> dict:
        critic_calls["count"] += 1
        raise AssertionError("critic must never be invoked after an infrastructure_error")

    graph = build_graph(
        planner_node=make_planner_node(planner_llm),
        retriever_node=_stub_retriever,
        generator_node=make_generator_node(generator_llm),
        static_check_node=make_static_check_node(pool),
        semantic_check_node=make_semantic_check_node(_oracle_loader),
        resource_check_node=make_resource_check_node(_oracle_loader),
        critic_node=spying_critic,
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "infrastructure_error"
    assert critic_calls["count"] == 0
    assert planner_llm.calls == 5  # tenacity's stop_after_attempt(5), see llm/base.py


# -- interrupt_before defaults to off ----------------------------------------


def test_interrupt_before_defaults_to_off(pool: WorkerPool, tmp_path: Path) -> None:
    graph, _, _ = _build(
        pool,
        tmp_path,
        generator_responses=[f"```python\n{VALID_BELL_CODE}```"],
        critic_responses=[],
    )
    # No interrupt configured: a single .invoke() runs the whole graph to a
    # terminal status without needing a checkpointer or a resume call.
    result = graph.invoke(_initial_state())
    assert result["status"] == "success"


def test_interrupt_before_pauses_between_semantic_and_resource_check(
    pool: WorkerPool, tmp_path: Path
) -> None:
    from langgraph.checkpoint.memory import InMemorySaver

    planner_llm = ScriptedLLMClient([REQUIREMENTS_JSON], tmp_path / "planner_cache")
    generator_llm = ScriptedLLMClient(
        [f"```python\n{VALID_BELL_CODE}```"], tmp_path / "generator_cache"
    )
    critic_llm = ScriptedLLMClient([], tmp_path / "critic_cache")

    compiled = build_graph(
        planner_node=make_planner_node(planner_llm),
        retriever_node=_stub_retriever,
        generator_node=make_generator_node(generator_llm),
        static_check_node=make_static_check_node(pool),
        semantic_check_node=make_semantic_check_node(_oracle_loader),
        resource_check_node=make_resource_check_node(_oracle_loader),
        critic_node=make_critic_node(critic_llm, max_iter=5),
        interrupt_before=["resource_check"],
        checkpointer=InMemorySaver(),
    )
    config = {"configurable": {"thread_id": "interrupt-test"}}

    state = compiled.invoke(_initial_state(), config=config)

    # Paused before resource_check: semantic is populated, resource is not,
    # and status is still the AgentState default ("running" is never set
    # explicitly, so the key is simply absent) rather than a terminal value.
    assert state.get("semantic") is not None
    assert state.get("resource") is None
    assert state.get("status") not in ("success", "failed_static", "failed_semantic", "aborted")


# -- recursion_limit: LangGraph's default (25 steps) undercounts a full
# MAX_ITER=5 retry loop through the worst-case validator cascade -----------


def test_default_recursion_limit_is_insufficient_for_a_full_retry_budget(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Regression test for a real failure hit against a live Ollama model:
    every retry iteration that reaches resource_check costs 6 graph steps
    (retriever, generator, static_check, semantic_check, resource_check,
    critic). At the default MAX_ITER=5 that is 30+ steps against LangGraph's
    default recursion_limit of 25 — `GraphRecursionError`, not a clean
    terminal status. This asserts the failure mode still exists (so nobody
    "fixes" it by silently relying on a raised default elsewhere) and that
    `recursion_limit_for` actually provides enough headroom for the true
    worst case.
    """
    from langgraph.errors import GraphRecursionError

    from qcagent.graph import recursion_limit_for

    heavy_responses = [f"```python\n{HEAVY_BELL_CODE}```"] * 5

    graph_no_limit, _, _ = _build(
        pool,
        tmp_path / "no_limit",
        generator_responses=heavy_responses,
        critic_responses=[CRITIC_HINT_JSON] * 4,
        resource_opt_level=0,
    )
    with pytest.raises(GraphRecursionError):
        graph_no_limit.invoke(_initial_state())

    graph_with_limit, _, _ = _build(
        pool,
        tmp_path / "with_limit",
        generator_responses=heavy_responses,
        critic_responses=[CRITIC_HINT_JSON] * 4,
        resource_opt_level=0,
    )
    result = graph_with_limit.invoke(
        _initial_state(), config={"recursion_limit": recursion_limit_for(5)}
    )

    assert result["status"] == "aborted"
    assert result["iteration"] == 5
    assert all(e.error_type == "ResourceExcess" for e in result["error_history"])


# -- state hygiene: static/semantic/resource/decision hold ONLY the current
# attempt (data-model.md) and must not leak stale values across iterations --


def test_semantic_is_cleared_when_a_later_attempt_fails_at_static(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Regression test for a real failure hit against a live model: iteration
    1 gets far enough to populate `semantic` (and fails there — wrong gate,
    not a Bell state), iteration 2 fails at static_check and must never run
    semantic_check at all. Before the fix, nothing cleared `semantic` when a
    new attempt began, so it still held iteration 1's stale verdict even
    though iteration 2 never got past static_check.
    """
    wrong_gate_code = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.x(0)\n"
    max_iter = 2
    graph, generator_llm, critic_llm = _build(
        pool,
        tmp_path,
        generator_responses=[
            f"```python\n{wrong_gate_code}```",  # iteration 1: fails semantic
            f"```python\n{BROKEN_CODE}```",  # iteration 2: fails static
        ],
        critic_responses=[CRITIC_HINT_JSON],  # only the iteration-1 retry needs a hint
        max_iter=max_iter,
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "failed_static"
    assert result["iteration"] == max_iter
    assert (
        result["semantic"] is None
    )  # never ran on iteration 2 — must not show iteration 1's leftover
    assert result["resource"] is None
    assert result["static"] is not None
    assert result["static"].error is not None
    assert result["static"].error.error_type == "SyntaxError"
    assert result["static"].error.iteration == 2  # patched onto the stored result, not hardcoded 0

    # error_history still accumulates across both iterations — only the
    # per-attempt fields are reset, per data-model.md.
    assert [e.iteration for e in result["error_history"]] == [1, 2]
    assert [e.error_type for e in result["error_history"]] == [
        "WrongGateDecomposition",
        "SyntaxError",
    ]


# -- D3c: state-preparation oracle at the full graph level -------------------


GHZ3_CHAIN_ORACLE = QuantumCircuit(3)
GHZ3_CHAIN_ORACLE.h(0)
GHZ3_CHAIN_ORACLE.cx(0, 1)
GHZ3_CHAIN_ORACLE.cx(1, 2)

# The exact circuit a live Ollama run produced for the ghz_3q task
# (research.md D3c): a CX star (0->1, 0->2) instead of the oracle's CX chain
# (0->1, 1->2). Both prepare the GHZ state from |000>, but `check_unitary`
# rejected it — the task's prompt only ever specified the output state.
GHZ3_STAR_CODE = (
    "from qiskit import QuantumCircuit\nqc = QuantumCircuit(3)\nqc.h(0)\nqc.cx(0, 1)\nqc.cx(0, 2)\n"
)

GHZ_REQUIREMENTS_JSON = json.dumps(
    {
        "satisfiable": True,
        "rejection_reason": None,
        "requirements": [
            {"id": "r1", "kind": "n_qubits", "description": "3 qubits", "value": 3},
            {"id": "r2", "kind": "property", "description": "produce a GHZ state", "value": None},
        ],
    }
)


def test_statevector_oracle_accepts_a_different_valid_state_preparation(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """D3c regression, at the full graph level (not just semantic.py's unit
    tests): reclassifying ghz_3q as oracle_kind="statevector" must let the
    live-observed CX-star circuit succeed, AND resource_check must still run
    — the routing fix keys off `verification_method`, not `unitary_equiv`
    (which stays None for a statevector-oracle pass), specifically so a
    state-prep task doesn't lose resource comparison as a side effect.
    """

    def ghz_oracle_loader(_ref: str) -> StatePreparationOracle:
        return StatePreparationOracle(reference_circuit=GHZ3_CHAIN_ORACLE)

    planner_llm = ScriptedLLMClient([GHZ_REQUIREMENTS_JSON], tmp_path / "planner_cache")
    generator_llm = ScriptedLLMClient(
        [f"```python\n{GHZ3_STAR_CODE}```"], tmp_path / "generator_cache"
    )
    critic_llm = ScriptedLLMClient([], tmp_path / "critic_cache")

    graph = build_graph(
        planner_node=make_planner_node(planner_llm, max_qubits=20),
        retriever_node=_stub_retriever,
        generator_node=make_generator_node(generator_llm),
        static_check_node=make_static_check_node(pool),
        semantic_check_node=make_semantic_check_node(ghz_oracle_loader),
        resource_check_node=make_resource_check_node(ghz_oracle_loader),
        critic_node=make_critic_node(critic_llm, max_iter=5),
    )

    result = graph.invoke(
        {
            "task_id": "t-ghz3",
            "spec": "Build a 3-qubit GHZ state: (|000> + |111>) / sqrt(2), up to global phase",
            "oracle_ref": "ghz_3q",
            "coupling_map_name": None,
            "iteration": 0,
        }
    )

    assert result["status"] == "success"
    assert result["iteration"] == 1
    assert result["semantic"].state_equiv is True
    assert result["semantic"].unitary_equiv is None
    assert result["resource"] is not None  # not skipped despite unitary_equiv=None
