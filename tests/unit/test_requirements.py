"""Tests for validators/requirements.py (T091, FR-009) — reference-free
checking of planner-extracted requirements against the generated circuit.

The tri-state (`passed=None`, "not checkable") carries most of the weight
here: requirements come from an LLM, so the checker must distinguish "the
circuit is wrong" from "the requirement isn't in a form I can check", and
must never report the second as the first.
"""

import pytest
from pydantic import ValidationError
from qiskit import QuantumCircuit

from qcagent.nodes.planner import _parse_planner_response
from qcagent.state import Requirement
from qcagent.validators.requirements import check_requirements


def _req(kind: str, value=None, rid: str = "r1") -> Requirement:
    return Requirement(id=rid, kind=kind, description="desc", value=value)


def _bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


# ---------------------------------------------------------------------------
# n_qubits
# ---------------------------------------------------------------------------


def test_n_qubits_match_passes() -> None:
    (outcome,) = check_requirements([_req("n_qubits", 2)], _bell())
    assert outcome.passed is True
    assert "2 qubits" in outcome.detail


def test_n_qubits_mismatch_fails_and_names_both_numbers() -> None:
    (outcome,) = check_requirements([_req("n_qubits", 3)], _bell())
    assert outcome.passed is False
    assert "circuit has 2 qubits" in outcome.detail
    assert "requirement states 3" in outcome.detail


def test_n_qubits_non_integer_is_not_checkable_not_failed() -> None:
    """A planner that emitted "three" instead of 3 says nothing about the
    circuit — reporting that as a FAILURE would blame the generated circuit
    for an extraction problem upstream of it."""
    (outcome,) = check_requirements([_req("n_qubits", "three")], _bell())
    assert outcome.passed is None
    assert "not checkable" in outcome.detail


@pytest.mark.parametrize("malformed", [True, False, 3.0])
def test_out_of_contract_values_are_refused_at_the_requirement_boundary(malformed) -> None:
    """Regression guard for the coercion this replaced: with lax `int`,
    `true` became a 1-qubit requirement, `false` a 0-qubit one, and `3.0`
    became 3 — each then CHECKED as if the planner had meant it. StrictInt
    refuses all three at construction, before any checker sees them."""
    with pytest.raises(ValidationError):
        _req("n_qubits", malformed)


def test_planner_response_with_bool_value_is_refused_not_interpreted() -> None:
    """End of the same path as it actually runs: planner.py's JSON parse."""
    text = (
        '{"satisfiable": true, "rejection_reason": null, "requirements": '
        '[{"id": "r1", "kind": "n_qubits", "description": "d", "value": true}]}'
    )
    with pytest.raises(ValidationError):
        _parse_planner_response(text)


def test_numeric_string_stays_a_string_and_is_not_checkable() -> None:
    """Unchanged by StrictInt, and deliberately so: `"3"` is in-contract as
    a string, so it is carried through and then reported not checkable by
    T091 rather than guessed at."""
    requirement = _req("n_qubits", "3")
    assert requirement.value == "3"
    (outcome,) = check_requirements([requirement], _bell())
    assert outcome.passed is None


# ---------------------------------------------------------------------------
# gate_set
# ---------------------------------------------------------------------------


def test_gate_set_subset_passes() -> None:
    (outcome,) = check_requirements([_req("gate_set", ["h", "cx"])], _bell())
    assert outcome.passed is True


def test_gate_set_superset_fails_and_names_the_offending_gates() -> None:
    qc = _bell()
    qc.t(0)
    (outcome,) = check_requirements([_req("gate_set", ["h", "cx"])], qc)
    assert outcome.passed is False
    assert "t" in outcome.detail


def test_gate_set_is_case_insensitive_on_the_requirement_side() -> None:
    (outcome,) = check_requirements([_req("gate_set", ["H", "CX"])], _bell())
    assert outcome.passed is True


def test_gate_set_with_unknown_gate_name_is_not_checkable_not_failed() -> None:
    """ "hadamard" is not a Qiskit instruction name. Every circuit would
    fail against it — which would be blaming the circuit for the planner's
    vocabulary."""
    (outcome,) = check_requirements([_req("gate_set", ["hadamard", "cnot"])], _bell())
    assert outcome.passed is None
    assert "not checkable" in outcome.detail
    assert "hadamard" in outcome.detail


def test_gate_set_non_list_is_not_checkable() -> None:
    (outcome,) = check_requirements([_req("gate_set", "h, cx")], _bell())
    assert outcome.passed is None


def test_gate_set_empty_list_is_not_checkable() -> None:
    (outcome,) = check_requirements([_req("gate_set", [])], _bell())
    assert outcome.passed is None


# ---------------------------------------------------------------------------
# Scope — unhandled kinds produce NO outcome, never a passing one
# ---------------------------------------------------------------------------


def test_unhandled_kinds_produce_no_outcome_at_all() -> None:
    """Emitting a passing outcome for `property`/`output_format`/`resource`
    would claim a check that never ran — the exact verification-verb
    borrowing this module exists to avoid."""
    requirements = [
        _req("property", "prepares a GHZ state", rid="r1"),
        _req("output_format", "measure all qubits", rid="r2"),
        _req("resource", "depth under 10", rid="r3"),
    ]
    assert check_requirements(requirements, _bell()) == []


def test_mixed_kinds_only_checkable_ones_appear_in_order() -> None:
    requirements = [
        _req("property", "prepares a Bell state", rid="r1"),
        _req("n_qubits", 2, rid="r2"),
        _req("output_format", "measure", rid="r3"),
        _req("gate_set", ["h", "cx"], rid="r4"),
    ]
    outcomes = check_requirements(requirements, _bell())
    assert [o.requirement.id for o in outcomes] == ["r2", "r4"]
    assert all(o.passed is True for o in outcomes)


def test_no_requirements_gives_no_outcomes() -> None:
    assert check_requirements([], _bell()) == []


def test_gate_set_ignores_measurement_and_barrier() -> None:
    """The real 7B planner emitted `['H', 'CX']`; a measured H+CX circuit
    must satisfy it (found end to end, T092)."""
    qc = _bell()
    qc.measure_all()
    (outcome,) = check_requirements([_req("gate_set", ["H", "CX"])], qc)
    assert outcome.passed is True, outcome.detail
