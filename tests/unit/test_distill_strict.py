"""The strict comparison forgives a global phase and nothing else."""

from __future__ import annotations

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT

from qcagent.distill.strict import (
    circuit_state,
    circuit_unitary,
    circuits_equal_state,
    circuits_equal_unitary,
    distributions_equal,
    states_equal,
    unitaries_equal,
)


def test_a_global_phase_is_forgiven() -> None:
    a = QuantumCircuit(2)
    a.h(0)
    a.cx(0, 1)
    b = a.copy()
    b.global_phase = 1.234
    assert circuits_equal_unitary(a, b).equal and circuits_equal_state(a, b).equal


def test_a_bit_reversed_circuit_is_not_equivalent() -> None:
    cx01, cx10 = QuantumCircuit(2), QuantumCircuit(2)
    cx01.cx(0, 1)
    cx10.cx(1, 0)
    assert not circuits_equal_unitary(cx01, cx10).equal


def test_a_bit_reversed_state_is_not_equivalent() -> None:
    low, high = QuantumCircuit(3), QuantumCircuit(3)
    low.x(0)  # |001>
    high.x(2)  # |100>
    result = circuits_equal_state(low, high)
    assert not result.equal and result.max_abs_diff > 0.5


def test_qft_without_its_swaps_is_not_the_qft() -> None:
    with_swaps = QFT(3, do_swaps=True).decompose()
    without = QFT(3, do_swaps=False).decompose()
    assert not unitaries_equal(circuit_unitary(with_swaps), circuit_unitary(without)).equal


def test_different_shapes_are_unequal_not_an_error() -> None:
    assert not states_equal(np.ones(4) / 2, np.ones(8) / np.sqrt(8)).equal
    assert not distributions_equal(np.array([0.5, 0.5]), np.array([1.0])).equal


def test_the_state_helper_refuses_a_circuit_without_a_pure_state() -> None:
    qc = QuantumCircuit(1, 1)
    qc.measure(0, 0)
    qc.x(0)
    try:
        circuit_state(qc)
    except ValueError as exc:
        assert "pure output state" in str(exc)
    else:
        raise AssertionError("a mid-circuit measurement has no pure state")
