"""Trap-case tests for semantic verification (T023) and the D3b checkpoint
(T023b) — see contracts/validators.md."""

import numpy as np
import pytest
from qiskit import QuantumCircuit

from qcagent.validators.semantic import (
    _check_by_composition,
    _check_exact,
    check_unitary,
    check_with_endianness,
)


def _ghz(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(0)
    for q in range(1, n):
        qc.cx(0, q)
    return qc


# -- TRAP 1: global phase (FR-004) -------------------------------------------


def test_global_phase_alone_does_not_cause_a_mismatch() -> None:
    """Two circuits differing only by e^{iθ} must be reported equivalent —
    this is the whole reason `Operator.equiv()` is mandated over
    `np.allclose` on the raw matrices."""
    reference = QuantumCircuit(2)
    reference.h(0)
    reference.cx(0, 1)

    generated = QuantumCircuit(2)
    generated.h(0)
    generated.cx(0, 1)
    generated.global_phase = np.pi / 3

    verdict = check_unitary(generated, reference, n_qubits=2)
    assert verdict.equivalent
    assert verdict.fidelity == pytest.approx(1.0)


def test_naive_matrix_comparison_would_have_failed() -> None:
    """Sanity check that the global-phase case above is non-trivial: a
    direct matrix comparison (the thing the contract says never to do)
    really would call these circuits unequal, which is exactly the trap
    `Operator.equiv()` exists to avoid."""
    from qiskit.quantum_info import Operator

    reference = QuantumCircuit(2)
    reference.h(0)
    reference.cx(0, 1)

    generated = QuantumCircuit(2)
    generated.h(0)
    generated.cx(0, 1)
    generated.global_phase = np.pi / 3

    assert not np.allclose(Operator(generated).data, Operator(reference).data)


# -- TRAP 2: endianness / bit-ordering convention (FR-005) ------------------


def test_endianness_swap_is_reported_as_its_own_category() -> None:
    generated = QuantumCircuit(3)
    generated.x(0)
    reference = generated.reverse_bits()  # only matches generated when re-reversed

    result = check_with_endianness(generated, reference, n_qubits=3)

    assert result.endianness_swapped is True
    assert result.passed is False
    assert result.unitary_equiv is False
    assert result.error is not None
    assert result.error.error_type == "EndiannessSwap"
    # The reversed check DID match here — the payload must say so.
    assert result.error.payload["reversed_bit_order_matches"] is True
    assert result.error.payload["expected_n_qubits"] == 3
    assert result.error.payload["actual_n_qubits"] == 3


def test_endianness_check_does_not_mask_genuine_functional_errors() -> None:
    """A circuit that matches NEITHER the reference NOR its bit-reversal
    must not be misreported as an endianness issue."""
    generated = QuantumCircuit(2)
    generated.x(0)
    reference = QuantumCircuit(2)
    reference.h(0)
    reference.h(1)

    result = check_with_endianness(generated, reference, n_qubits=2)

    assert result.endianness_swapped is False
    assert result.passed is False
    assert result.error is not None
    assert result.error.error_type != "EndiannessSwap"


def test_wrong_gate_decomposition_payload_carries_structural_diff() -> None:
    """A bare fidelity scalar says "wrong" but not "wrong how" — payload
    must carry a diff a retry can actually act on: qubit count, gate counts
    by type on both sides, and whether the reversed-bit-order check also
    failed. All computed from properties `check_unitary` already has
    (`.num_qubits`, `.count_ops()`) — no extra simulation.
    """
    reference = QuantumCircuit(2)
    reference.h(0)
    reference.cx(0, 1)

    generated = QuantumCircuit(2)
    generated.x(0)
    generated.x(1)

    result = check_with_endianness(generated, reference, n_qubits=2)

    assert result.error is not None
    assert result.error.error_type == "WrongGateDecomposition"
    payload = result.error.payload
    assert payload["expected_n_qubits"] == 2
    assert payload["actual_n_qubits"] == 2
    assert payload["expected_gate_counts"] == {"h": 1, "cx": 1}
    assert payload["actual_gate_counts"] == {"x": 2}
    assert payload["reversed_bit_order_matches"] is False
    assert "direct_fidelity" in payload
    assert "reversed_bit_order_fidelity" in payload
    assert payload["expected_gate_sequence"] == [["h", [0]], ["cx", [0, 1]]]
    assert payload["actual_gate_sequence"] == [["x", [0]], ["x", [1]]]


def test_payload_gate_sequence_distinguishes_same_counts_different_qubits() -> None:
    """The exact trap gate counts alone can't catch: identical gate counts
    (cx: 2, h: 1 on both sides) but the h lands on a different qubit — a
    genuinely different circuit that a counts-only diff would report as
    "everything matches"."""
    reference = QuantumCircuit(3)
    reference.h(0)
    reference.cx(0, 1)
    reference.cx(1, 2)

    generated = QuantumCircuit(3)
    generated.h(1)
    generated.cx(0, 1)
    generated.cx(1, 2)

    result = check_with_endianness(generated, reference, n_qubits=3)

    assert result.error is not None
    payload = result.error.payload
    # Same gate counts on both sides — this is exactly the case the counts
    # table alone can't distinguish.
    assert payload["expected_gate_counts"] == payload["actual_gate_counts"] == {"h": 1, "cx": 2}
    assert payload["expected_gate_sequence"] == [["h", [0]], ["cx", [0, 1]], ["cx", [1, 2]]]
    assert payload["actual_gate_sequence"] == [["h", [1]], ["cx", [0, 1]], ["cx", [1, 2]]]


# -- Incompatible dimensions -------------------------------------------------


def test_incompatible_dimensions_do_not_raise() -> None:
    generated = QuantumCircuit(2)
    generated.h(0)
    reference = QuantumCircuit(3)
    reference.h(0)

    verdict = _check_exact(generated, reference)

    assert verdict.equivalent is False
    assert verdict.reason == "dim_mismatch"
    assert verdict.fidelity == 0.0


# -- T023b: D3b checkpoint — exact and composition paths must agree ---------


def test_exact_and_composition_agree_on_equivalent_8_qubit_circuits() -> None:
    """T023b. If the two verification paths disagree, switching methods
    above EXACT_UNITARY_MAX_QUBITS introduces bias into the correctness
    metric — this is exactly what D3b requires us to rule out."""
    n_qubits = 8
    generated = _ghz(n_qubits)
    reference = _ghz(n_qubits)

    exact = _check_exact(generated, reference)
    composition = _check_by_composition(generated, reference, n_qubits=n_qubits)

    assert exact.method == "exact"
    assert composition.method == "composition"
    assert exact.equivalent == composition.equivalent
    assert exact.equivalent is True


def test_exact_and_composition_agree_on_non_equivalent_8_qubit_circuits() -> None:
    """Same checkpoint, negative direction: agreeing only on the "yes,
    equivalent" case wouldn't rule out one method being trivially
    permissive. Both must also agree when the circuits genuinely differ."""
    n_qubits = 8
    generated = _ghz(n_qubits)
    different = QuantumCircuit(n_qubits)
    different.x(0)  # nowhere near a GHZ state

    exact = _check_exact(generated, different)
    composition = _check_by_composition(generated, different, n_qubits=n_qubits)

    assert exact.equivalent == composition.equivalent
    assert exact.equivalent is False
