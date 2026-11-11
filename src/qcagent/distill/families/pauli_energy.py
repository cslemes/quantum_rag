"""Family 4: random local Pauli Hamiltonians, ground energy (energy).

No closed form in general, so two independent constructions of the matrix check
each other, and two analytic limit cases calibrate both:
  * a single term c*P has ground energy -|c|;
  * a diagonal Hamiltonian (only I and Z) has ground energy equal to the minimum
    over bitstrings, enumerated directly.

Convention, this family's analogue of a boundary condition: Pauli labels follow
Qiskit, the LEFTMOST character acts on the HIGHEST qubit, the rightmost on
qubit 0. Builder A is `SparsePauliOp.to_matrix()` with `eigvalsh`; builder B
writes the 2x2 matrices out, takes the kron in the declared order, and uses a
sparse `eigsh`. Independence is limited to how the matrix is built and
diagonalised; the calibration cases bound what that can miss.

What the label order does and does not decide: the lowest eigenvalue is a
spectrum, invariant under relabelling the qubits, so the ORACLE energy cannot
disagree between builders because of endianness (and the calibration cases,
likewise, would not catch a reversal). The order decides which STATE reaches that
energy, so it is exercised where a state is involved: the reference circuit built
from builder A's eigenvector must pass `check_energy`, and a teacher's circuit is
judged by the expectation of H under this label order.

The task is an energy-kind task like the H2 ones: build a circuit whose state
reaches the exact ground energy, judged by the cascade's `check_energy`,
unchanged.
"""

from __future__ import annotations

import itertools
import random

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import StatePreparation
from qiskit.quantum_info import SparsePauliOp
from scipy.sparse import csr_matrix
from scipy.sparse import kron as sparse_kron
from scipy.sparse.linalg import ArpackError, eigsh

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.validators.semantic import check_energy

ENERGY_TOL = 1e-2  # the cascade's own default, the same as the H2 tasks

_PAULI = {
    "I": np.array([[1, 0], [0, 1]], dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}
COEFF_GRID = [c * 0.25 for c in range(-8, 9) if c != 0]


def ground_energy_a(labels: list[str], coeffs: list[float]) -> float:
    matrix = SparsePauliOp(labels, coeffs=coeffs).to_matrix()
    return float(np.linalg.eigvalsh(matrix)[0])


def ground_energy_b(labels: list[str], coeffs: list[float]) -> float:
    """Hand-built kron, leftmost label character the most significant factor."""
    n = len(labels[0])
    total = csr_matrix((1 << n, 1 << n), dtype=complex)
    for label, coeff in zip(labels, coeffs, strict=True):
        term = csr_matrix(np.eye(1, dtype=complex))
        for char in label:  # leftmost first: the highest qubit is the outer factor
            term = sparse_kron(term, csr_matrix(_PAULI[char]), format="csr")
        total = total + coeff * term
    v0 = np.ones(1 << n) / np.sqrt(1 << n)
    try:
        return float(eigsh(total, k=1, which="SA", v0=v0, return_eigenvectors=False)[0])
    except ArpackError:
        # The uniform vector is a null vector of some H (e.g. 0.75*XIIX - 0.75*XIII), so the
        # Krylov space is empty. A fixed-seed random start is the fallback; the uniform start
        # stays first so every result already recorded is reproduced unchanged.
        v0 = np.random.default_rng(0).standard_normal(1 << n)
        return float(eigsh(total, k=1, which="SA", v0=v0, return_eigenvectors=False)[0])


def ground_state_circuit(labels: list[str], coeffs: list[float]) -> QuantumCircuit:
    """A reference circuit reaching the ground energy: state preparation of an
    exact ground vector. Used to confirm the oracle passes the cascade's check."""
    matrix = SparsePauliOp(labels, coeffs=coeffs).to_matrix()
    _, vectors = np.linalg.eigh(matrix)
    n = len(labels[0])
    circuit = QuantumCircuit(n)
    circuit.append(StatePreparation(vectors[:, 0]), range(n))
    return circuit


def _diagonal_minimum(labels: list[str], coeffs: list[float]) -> float:
    n = len(labels[0])
    best = float("inf")
    for bits in itertools.product((0, 1), repeat=n):  # bits[q] is the value of qubit q
        energy = 0.0
        for label, coeff in zip(labels, coeffs, strict=True):
            sign = 1
            for position, char in enumerate(label):
                if char == "Z" and bits[n - 1 - position]:
                    sign = -sign
            energy += coeff * sign
        best = min(best, energy)
    return best


def _random_term(rng: random.Random, n: int) -> str:
    weight = rng.choice((1, 2, 2, 3))
    qubits = rng.sample(range(n), min(weight, n))
    chars = ["I"] * n
    for q in qubits:
        chars[n - 1 - q] = rng.choice("XYZ")
    return "".join(chars)


class PauliEnergy(Family):
    name = "pauli_hamiltonian_energy"
    oracle_kind = "energy"
    closed_form = False

    def variations(self, count: int = 20) -> list[Variation]:
        """The first 20 are the pilot's, unchanged (same rng stream). Beyond 20 the same stream
        continues with n drawn from 3..6 and duplicates skipped, so a larger set EXTENDS the pilot."""
        rng = random.Random("pauli_hamiltonian_energy-v1")
        out: list[Variation] = []
        seen: set[str] = set()
        pilot_sizes = [3] * 7 + [4] * 7 + [5] * 6
        while len(out) < count:
            index = len(out)
            n = pilot_sizes[index] if index < len(pilot_sizes) else rng.choice([3, 4, 5, 6])
            labels: list[str] = []
            n_terms = rng.randint(2, 5)
            while len(labels) < n_terms:
                label = _random_term(rng, n)
                if label not in labels:
                    labels.append(label)
            coeffs = [rng.choice(COEFF_GRID) for _ in labels]
            v = Variation(self.name, index, {"n": n, "labels": labels, "coeffs": coeffs})
            if v.key in seen:
                continue
            seen.add(v.key)
            out.append(v)
        return out

    def statement(self, v: Variation) -> str:
        n, labels, coeffs = v.params["n"], v.params["labels"], v.params["coeffs"]
        terms = " + ".join(f"({c}) * {lab}" for lab, c in zip(labels, coeffs, strict=True))
        return (
            f"Build a {n}-qubit circuit that prepares a ground state of the Hamiltonian "
            f"H = {terms}, where each term is a Pauli string in Qiskit's label order (the "
            f"leftmost character acts on qubit {n - 1}, the rightmost on qubit 0). The state "
            f"prepared from |0...0> must have expectation value of H within {ENERGY_TOL} of the "
            f"exact lowest eigenvalue of H. No measurement, no free Parameter objects."
        )

    def oracle(self, v: Variation) -> tuple[SparsePauliOp, float]:
        labels, coeffs = v.params["labels"], v.params["coeffs"]
        return SparsePauliOp(labels, coeffs=coeffs), ground_energy_a(labels, coeffs)

    def verify(self, v: Variation) -> Verification:
        labels, coeffs = v.params["labels"], v.params["coeffs"]
        a, b = ground_energy_a(labels, coeffs), ground_energy_b(labels, coeffs)
        _, exact = self.oracle(v)
        reference = check_energy(
            ground_state_circuit(labels, coeffs), SparsePauliOp(labels, coeffs=coeffs), exact
        )
        return Verification(
            v,
            [
                Check("builder_a_vs_builder_b", abs(a - b) <= 1e-9, abs(a - b)),
                Check(
                    "reference_circuit_passes_check_energy",
                    reference.passed,
                    reference.energy_error,
                ),
            ],
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        hamiltonian, exact = self.oracle(v)
        if circuit.num_qubits != v.params["n"]:
            return Check("check_energy", False, float("inf"), "wrong qubit count")
        verdict = check_energy(circuit, hamiltonian, exact, tol=ENERGY_TOL)
        return Check("check_energy", verdict.passed, verdict.energy_error)

    def calibrate(self) -> list[Check]:
        checks: list[Check] = []
        rng = random.Random("pauli-calibration-v1")
        for n in (2, 3, 4, 5):
            for char in "XYZ":
                label = "".join(rng.choice("IXYZ") for _ in range(n))
                label = label.replace("I", char, 1) if set(label) == {"I"} else label
                coeff = rng.choice(COEFF_GRID)
                for name, fn in (("a", ground_energy_a), ("b", ground_energy_b)):
                    got = fn([label], [coeff])
                    checks.append(
                        Check(
                            f"single_term_{label}_{coeff}_builder_{name}",
                            abs(got - (-abs(coeff))) <= 1e-9,
                            abs(got + abs(coeff)),
                            f"expected {-abs(coeff)}, got {got}",
                        )
                    )
        for n in (3, 4, 5):
            labels = []
            while len(labels) < 4:
                label = "".join(rng.choice("IZ") for _ in range(n))
                if set(label) != {"I"} and label not in labels:
                    labels.append(label)
            coeffs = [rng.choice(COEFF_GRID) for _ in labels]
            expected = _diagonal_minimum(labels, coeffs)
            for name, fn in (("a", ground_energy_a), ("b", ground_energy_b)):
                got = fn(labels, coeffs)
                checks.append(
                    Check(
                        f"diagonal_n{n}_builder_{name}",
                        abs(got - expected) <= 1e-9,
                        abs(got - expected),
                        f"expected {expected}, got {got}",
                    )
                )
        return checks
