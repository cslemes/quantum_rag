"""STEPS 2-4 of the family selection, as data and arithmetic.

The qualitative filters (a) oracle, (c) mechanism identity are recorded in `CANDIDATES`
with their reasons; the quantitative ones, (b) the count of distinct parameter
variations and (d) the oracle's time at the qubit counts used, are COMPUTED here.

Mechanism identity (filter c), the operational reading used, from textbook definitions
of the held-out FAMILIES (their names only; no held-out statement or reference is read):
a candidate has identity with a held-out family when (i) the held-out family is a
parameter specialisation of the candidate or the candidate of it (BV is DJ-balanced with
a linear oracle; QAOA with beta = 0 is H plus the cost layer), or (ii) the candidate's
reference construction contains the held-out family's WHOLE construction at 3 or more
qubits as a block (Draper adder contains the QFT; ripple-carry contains the full adder).
A shared primitive (one H and one CX) or an overlapping skeleton is ADJACENCY, reported
but not disqualifying. This reading is the one decision that moves the list most.
"""

from __future__ import annotations

import json
import time
from math import comb, factorial

import numpy as np
from qiskit.quantum_info import SparsePauliOp

from qcagent.distill.skills import ROOT

TARGET_STATEMENTS = 5000  # the figure the cost estimate used; a stated assumption


# ---- (b) distinct parameter variations, in the declared ranges ----------------------


def permutations_count(n_min: int = 3, n_max: int = 7) -> int:
    """Non-identity qubit permutations; n <= 7 keeps the unitary at 128 x 128."""
    return sum(factorial(n) - 1 for n in range(n_min, n_max + 1))


def connected_graph_count(n: int) -> int:
    from qcagent.distill.families.graph_states import connected_graphs

    return len(connected_graphs(n))


def stabilizer_graph_count(n_min: int = 4, n_max: int = 6) -> int:
    """Connected labelled graphs on 4..6 vertices, GHZ's local-Clifford class INCLUDED."""
    return sum(connected_graph_count(n) for n in range(n_min, n_max + 1))


def pauli_string_count(n: int, max_weight: int = 3) -> int:
    return sum(comb(n, w) * 3**w for w in range(1, max_weight + 1))


def pauli_hamiltonian_count(n_min: int = 3, n_max: int = 8, coeffs: int = 16) -> int:
    """2-5 distinct non-identity Pauli strings of weight <= 3, each with a coefficient
    on a 16-value grid (multiples of 0.25 in [-2, 2], zero excluded)."""
    return sum(
        comb(pauli_string_count(n), k) * coeffs**k
        for n in range(n_min, n_max + 1)
        for k in range(2, 6)
    )


def biased_bits_count(n_min: int = 3, n_max: int = 8, grid: int = 18) -> int:
    return sum(grid**n for n in range(n_min, n_max + 1))


def simon_count(n_min: int = 2, n_max: int = 6) -> int:
    """(period s, control position j in the set bits of s): n * 2^(n-1) per n; 2n qubits."""
    return sum(n * 2 ** (n - 1) for n in range(n_min, n_max + 1))


def grover_count(n_min: int = 3, n_max: int = 8, max_marked: int = 3) -> int:
    return sum(comb(2**n, m) for n in range(n_min, n_max + 1) for m in range(1, max_marked + 1))


def w_dicke_count(n_min: int = 3, n_max: int = 8, weights: int = 4) -> int:
    """Weighted W states (integer weights 1..4 over the weight-1 basis states); the
    uniform Dicke states are the n*(k) subset and are far fewer than 200 by themselves."""
    uniform = sum(n - 1 for n in range(n_min, 13))
    return uniform + sum(weights**n for n in range(n_min, n_max + 1))


CAPACITY = {
    "qubit_permutation": permutations_count,
    "stabilizer_graph_states": stabilizer_graph_count,
    "pauli_hamiltonian_energy": pauli_hamiltonian_count,
    "independent_biased_bits": biased_bits_count,
    "simon": simon_count,
    "grover": grover_count,
    "w_dicke": w_dicke_count,
}


# ---- (d) oracle time at the qubit counts used -----------------------------------------


def _seconds(fn) -> float:
    start = time.perf_counter()
    fn()
    return round(time.perf_counter() - start, 3)


def oracle_times() -> dict[str, dict[str, float]]:
    """Measured on this host (one BLAS thread not forced). The exact-diagonalisation wall
    is measured, not assumed."""
    rng = np.random.default_rng(0)

    def energy(n: int) -> float:
        labels = ["".join(rng.choice(list("IXYZ"), n)) for _ in range(5)]
        labels = [label if set(label) != {"I"} else "Z" + label[1:] for label in labels]
        op = SparsePauliOp(labels, coeffs=rng.uniform(-1, 1, 5))
        return _seconds(lambda: np.linalg.eigvalsh(op.to_matrix()))

    return {
        "pauli_energy_exact_diagonalisation_seconds": {str(n): energy(n) for n in (8, 10, 11, 12)},
    }


def table() -> dict:
    return {
        "target_statements": TARGET_STATEMENTS,
        "capacity": {name: fn() for name, fn in CAPACITY.items()},
        "oracle_times": oracle_times(),
    }


if __name__ == "__main__":
    result = table()
    (ROOT / "bench" / "family_selection_capacity.json").write_text(
        json.dumps(result, indent=1) + "\n"
    )
    print(json.dumps(result, indent=1))
