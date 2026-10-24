"""Strict equivalence: equal up to global phase, and nothing else.

The cascade's `check_with_endianness` variants accept a circuit whose qubit
order is reversed, because for a user's request that is a reasonable thing to
forgive. Here it would be wrong in a specific way: comparing two independent
constructions (or a construction and its closed-form oracle) is the operation
whose job is to expose a bit-order disagreement, and a tolerant check hides
exactly that. So there is no reversal search, no permutation search, no
tolerance wider than numerical noise, and a failed comparison says by how much.

Convention (every family): Qiskit little-endian, qubit 0 the least significant
bit, basis index k = sum_i b_i 2^i.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator, Statevector

from qcagent.validators.circuits import NotEvaluable, prepared_operator, prepared_statevector

ATOL = 1e-9


@dataclass(frozen=True)
class StrictResult:
    equal: bool
    max_abs_diff: float
    detail: str = ""


def _phase_aligned_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Largest entrywise difference after removing the one global phase that
    best aligns `b` to `a` (taken at a's largest entry, so it is not a fit)."""
    if a.shape != b.shape:
        return float("inf")
    k = int(np.argmax(np.abs(a)))
    if abs(a.flat[k]) < ATOL or abs(b.flat[k]) < ATOL:
        # The largest entry of one is a zero of the other: unequal outright.
        return float(np.max(np.abs(a - b)))
    phase = (a.flat[k] / b.flat[k]) / abs(a.flat[k] / b.flat[k])
    return float(np.max(np.abs(a - phase * b)))


def unitaries_equal(a: np.ndarray, b: np.ndarray, atol: float = ATOL) -> StrictResult:
    diff = _phase_aligned_diff(np.asarray(a, dtype=complex), np.asarray(b, dtype=complex))
    return StrictResult(diff <= atol, diff, "unitary, up to global phase")


def states_equal(a: np.ndarray, b: np.ndarray, atol: float = ATOL) -> StrictResult:
    diff = _phase_aligned_diff(np.asarray(a, dtype=complex).ravel(), np.asarray(b).ravel())
    return StrictResult(diff <= atol, diff, "statevector, up to global phase")


def distributions_equal(a: np.ndarray, b: np.ndarray, atol: float = ATOL) -> StrictResult:
    a, b = np.asarray(a, dtype=float).ravel(), np.asarray(b, dtype=float).ravel()
    diff = float("inf") if a.shape != b.shape else float(np.max(np.abs(a - b)))
    return StrictResult(diff <= atol, diff, "probabilities, index k = sum b_i 2^i")


def circuit_unitary(circuit: QuantumCircuit) -> np.ndarray:
    op = prepared_operator(circuit)
    if isinstance(op, NotEvaluable):
        raise ValueError(f"circuit has no unitary: {op.reason}")
    assert isinstance(op, Operator)
    return op.data


def circuit_state(circuit: QuantumCircuit) -> np.ndarray:
    state = prepared_statevector(circuit)
    if isinstance(state, NotEvaluable):
        raise ValueError(f"circuit has no pure output state: {state.reason}")
    assert isinstance(state, Statevector)
    return state.data


def circuits_equal_unitary(a: QuantumCircuit, b: QuantumCircuit) -> StrictResult:
    return unitaries_equal(circuit_unitary(a), circuit_unitary(b))


def circuits_equal_state(a: QuantumCircuit, b: QuantumCircuit) -> StrictResult:
    return states_equal(circuit_state(a), circuit_state(b))
