"""Tests for graph.py's `make_assertion_check_node` (T087) — the graph-level
adaptation around `validators/assertions.py`'s pure parser/evaluator (already
covered by tests/unit/test_assertions.py). This file only tests what T087
adds: empty-list-is-not-an-error, and turning violated/not-evaluable
outcomes into `ErrorRecord`s that `critic.py` can consume (FR-012).
"""

import io

from qiskit import QuantumCircuit, qpy

from qcagent.graph import make_assertion_check_node
from qcagent.state import Requirement, StaticResult
from qcagent.validators.assertions import parse_assertions


def _circuit_qpy(qc: QuantumCircuit) -> bytes:
    with io.BytesIO() as buf:
        qpy.dump(qc, buf)
        return buf.getvalue()


def _bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


def _static_ok(qc: QuantumCircuit) -> StaticResult:
    return StaticResult(parsed=True, executed=True, transpiled=True, circuit_qpy=_circuit_qpy(qc))


def test_no_assertions_declared_produces_empty_list_not_an_error() -> None:
    node = make_assertion_check_node()
    state = {"assertions": [], "static": _static_ok(_bell()), "iteration": 0}
    result = node(state)
    assert result["assertion_results"] == []
    assert "error_history" not in result or result.get("error_history") in ([], None)


def test_missing_assertions_key_treated_as_empty() -> None:
    node = make_assertion_check_node()
    state = {"static": _static_ok(_bell()), "iteration": 0}
    result = node(state)
    assert result["assertion_results"] == []


def test_all_passing_produces_no_error_records() -> None:
    node = make_assertion_check_node()
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    state = {"assertions": assertions, "static": _static_ok(_bell()), "iteration": 0}
    result = node(state)
    assert len(result["assertion_results"]) == 1
    assert result["assertion_results"][0].passed is True
    assert result["error_history"] == []


def test_violation_produces_assertion_violated_error_record() -> None:
    node = make_assertion_check_node()
    assertions = parse_assertions('MEASURES == "00"', 2)  # Bell never collapses to 00 alone
    state = {"assertions": assertions, "static": _static_ok(_bell()), "iteration": 2}
    result = node(state)
    assert result["assertion_results"][0].passed is False
    (record,) = result["error_history"]
    assert record.error_type == "AssertionViolated"
    # FR-012: `message` is what the generator's retry prompt renders (the
    # payload never reaches it), so the assertion's own text must be there.
    assert record.message.startswith('MEASURES == "00" — ')
    assert record.stage == "semantic"
    assert record.iteration == 2
    assert record.payload["assertion"]["kind"] == "measures"


def test_not_evaluable_produces_assertion_not_evaluable_error_record() -> None:
    node = make_assertion_check_node()
    only_00 = QuantumCircuit(2)  # stays |00>, amplitude of |11> is exactly 0
    assertions = parse_assertions("PHASE_DIFF(|00>,|11>) ~= 0", 2)
    state = {"assertions": assertions, "static": _static_ok(only_00), "iteration": 1}
    result = node(state)
    assert result["assertion_results"][0].passed is None
    (record,) = result["error_history"]
    assert record.error_type == "AssertionNotEvaluable"
    assert record.stage == "semantic"
    assert record.iteration == 1


def test_mixed_outcomes_only_error_records_for_non_passing_ones() -> None:
    node = make_assertion_check_node()
    text = 'PROBABILITY(|11>) ~= 0.5\nMEASURES == "00"'
    assertions = parse_assertions(text, 2)
    state = {"assertions": assertions, "static": _static_ok(_bell()), "iteration": 0}
    result = node(state)
    assert [o.passed for o in result["assertion_results"]] == [True, False]
    assert len(result["error_history"]) == 1
    assert result["error_history"][0].error_type == "AssertionViolated"


# ---------------------------------------------------------------------------
# T091 — requirement checking runs in this node too, including when the user
# declared no assertions at all (that is the whole point of FR-009).
# ---------------------------------------------------------------------------


def _requirement(kind: str, value) -> Requirement:
    return Requirement(id="r1", kind=kind, description="desc", value=value)


def test_requirements_are_checked_even_with_zero_assertions() -> None:
    node = make_assertion_check_node()
    state = {
        "assertions": [],
        "requirements": [_requirement("n_qubits", 2)],
        "static": _static_ok(_bell()),
        "iteration": 0,
    }
    result = node(state)
    assert result["assertion_results"] == []
    (outcome,) = result["requirement_results"]
    assert outcome.passed is True


def test_requirement_failure_is_reported_without_an_error_record() -> None:
    """A requirement violation is surfaced in the report and blocks a
    correctness claim, but does NOT enter the closed error taxonomy — that
    would put an LLM-extracted premise into the repair loop, a separate
    decision that has not been taken."""
    node = make_assertion_check_node()
    state = {
        "assertions": [],
        "requirements": [_requirement("n_qubits", 5)],
        "static": _static_ok(_bell()),
        "iteration": 0,
    }
    result = node(state)
    assert result["requirement_results"][0].passed is False
    assert "error_history" not in result


def test_requirements_checked_alongside_assertions() -> None:
    node = make_assertion_check_node()
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    state = {
        "assertions": assertions,
        "requirements": [_requirement("gate_set", ["h", "cx"])],
        "static": _static_ok(_bell()),
        "iteration": 0,
    }
    result = node(state)
    assert result["assertion_results"][0].passed is True
    assert result["requirement_results"][0].passed is True


def test_missing_requirements_key_treated_as_empty() -> None:
    node = make_assertion_check_node()
    result = node({"static": _static_ok(_bell()), "iteration": 0})
    assert result["requirement_results"] == []
