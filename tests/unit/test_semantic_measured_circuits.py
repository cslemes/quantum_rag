"""Reference checks against MEASURED generated code (bug 11).

Real generated code ends in `measure_all()` constantly. Every unit test for
`semantic.py` used bare, measurement-free circuits, so no test ever drove one
into the oracle paths — and the first live suite run died on the first task
that reached `semantic_check`, taking all 360 runs with it.

The assertion evaluator had already been fixed for exactly this (T092) and
grew its own private measurement-stripping. The oracle paths kept the bug,
which is why the primitive now lives in `validators/circuits.py` and both
callers share it. These tests exist to keep that true.

Two rules, per path:

* a FINAL measurement must not change the verdict — it samples the prepared
  state, it doesn't change it;
* a NON-FINAL measurement must make the check decline to answer: not a
  crash, and above all not a pass.
"""

import pytest
from qiskit import QuantumCircuit

from qcagent.validators.circuits import NotEvaluable, no_pure_state_reason, prepared_statevector
from qcagent.validators.semantic import (
    check_statevector,
    check_statevector_with_endianness,
    check_unitary,
    check_with_endianness,
)


def _bell(*, measured: bool = False, mid_circuit: bool = False) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    if mid_circuit:
        qc.measure_all()  # a measurement that is NOT final once gates follow
        qc.cx(0, 1)
        return qc
    qc.cx(0, 1)
    if measured:
        qc.measure_all()
    return qc


REFERENCE = _bell()


# --- final measurements are invisible to the verdict -----------------------


def test_statevector_oracle_accepts_a_measured_circuit() -> None:
    verdict = check_statevector(_bell(measured=True), REFERENCE)
    assert verdict.equivalent, "measure_all() at the end must not change the state compared"
    assert not verdict.not_evaluable


def test_unitary_oracle_accepts_a_measured_circuit() -> None:
    assert check_unitary(_bell(measured=True), REFERENCE, n_qubits=2).equivalent


def test_composition_path_accepts_a_measured_circuit() -> None:
    # n_qubits > EXACT_UNITARY_MAX_QUBITS forces the 2^n path, the one that
    # must not build a 4^n operator just to test evaluability.
    wide = QuantumCircuit(13)
    wide.h(0)
    wide.cx(0, 1)
    reference = wide.copy()
    wide.measure_all()
    assert check_unitary(wide, reference, n_qubits=13).equivalent


@pytest.mark.parametrize(
    "check",
    [
        lambda g: check_statevector_with_endianness(g, REFERENCE),
        lambda g: check_with_endianness(g, REFERENCE, 2),
    ],
    ids=["statevector", "unitary"],
)
def test_endianness_wrappers_pass_a_measured_correct_circuit(check) -> None:
    result = check(_bell(measured=True))
    assert result.passed is True
    assert result.error is None


# --- a non-final measurement means "cannot answer", never "passed" ---------


@pytest.mark.parametrize(
    "check",
    [
        lambda g: check_statevector_with_endianness(g, REFERENCE),
        lambda g: check_with_endianness(g, REFERENCE, 2),
    ],
    ids=["statevector", "unitary"],
)
def test_mid_circuit_measurement_declines_instead_of_crashing(check) -> None:
    result = check(_bell(mid_circuit=True))

    assert result.passed is False, "a check that cannot run must never pass"
    # None, not False: no comparison happened, so neither field may claim one
    # did. report.py reads these to decide `functional_correctness_verified`.
    assert result.unitary_equiv is None
    assert result.state_equiv is None
    assert result.error is not None
    assert result.error.error_type == "NonUnitaryCircuit"
    assert result.error.payload["not_evaluable"] is True
    # No fabricated similarity score anywhere in what a human reads.
    assert "0.0000" not in result.error.message


def test_verdicts_mark_not_evaluable_apart_from_a_measured_difference() -> None:
    declined = check_statevector(_bell(mid_circuit=True), REFERENCE)
    genuinely_different = check_statevector(QuantumCircuit(2), REFERENCE)

    assert declined.not_evaluable
    assert not genuinely_different.not_evaluable
    # Both are equivalent=False — that is the safe direction — but only one
    # of them measured anything.
    assert not declined.equivalent and not genuinely_different.equivalent


# --- the shared primitive -------------------------------------------------


def test_structural_check_agrees_with_the_simulator() -> None:
    """The cheap pre-check and the expensive constructor must classify the
    same circuits the same way, or the composition path silently diverges
    from the exact path."""
    for circuit in (_bell(), _bell(measured=True), _bell(mid_circuit=True)):
        structural = no_pure_state_reason(circuit) is not None
        simulated = isinstance(prepared_statevector(circuit), NotEvaluable)
        assert structural == simulated, circuit


# --- unbound parameters (bug 19) -------------------------------------------


def _parametrized() -> QuantumCircuit:
    from qiskit.circuit import Parameter

    qc = QuantumCircuit(2)
    qc.rx(Parameter("theta"), 0)
    qc.cx(0, 1)
    return qc


def test_an_unbound_parameter_is_not_evaluable_rather_than_a_crash() -> None:
    """Bug 19. A parametrized ansatz describes a FAMILY of states, so there
    is nothing to compare against a reference.

    Qiskit signals this with a bare `TypeError` out of float conversion, NOT
    a `QiskitError` — which is how it escaped `except QiskitError` and
    crashed 15 runs of the first live suite. `semantic.py` had documented
    exactly that TypeError for `check_energy` and never applied it here.
    """
    circuit = _parametrized()

    assert no_pure_state_reason(circuit) is not None
    assert isinstance(prepared_statevector(circuit), NotEvaluable)


@pytest.mark.parametrize(
    "check",
    [
        lambda g: check_statevector_with_endianness(g, REFERENCE),
        lambda g: check_with_endianness(g, REFERENCE, 2),
    ],
    ids=["statevector", "unitary"],
)
def test_both_oracle_paths_decline_a_parametrized_circuit(check) -> None:
    """Both entry points failed in the live run — the operator path as well
    as the statevector one — so both are pinned here."""
    result = check(_parametrized())

    assert result.passed is False, "a check that cannot run must never pass"
    assert result.unitary_equiv is None
    assert result.state_equiv is None
    assert result.error.error_type == "NonUnitaryCircuit"


def test_the_reason_names_the_parameter() -> None:
    """After an unattended run, "not evaluable" without saying which
    parameter is unbound is not actionable."""
    assert "theta" in no_pure_state_reason(_parametrized())
