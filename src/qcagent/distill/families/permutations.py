"""Family 1: qubit permutations (unitary).

Definition (the oracle): for a permutation pi of the n qubits, the unitary that
moves the state of qubit i onto qubit pi(i):
    P |b_{n-1} .. b_0> = |c_{n-1} .. c_0>,   c_{pi(i)} = b_i.
It is written down as a permutation matrix over basis indices by bit
manipulation. The construction is a SWAP circuit from the cycle decomposition;
it shares no code with the definition.
"""

from __future__ import annotations

import itertools
import random

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_unitary, unitaries_equal


def permutation_unitary(pi: list[int]) -> np.ndarray:
    """The oracle: output index has bit pi(i) equal to input bit i."""
    n = len(pi)
    matrix = np.zeros((1 << n, 1 << n), dtype=complex)
    for b in range(1 << n):
        c = 0
        for i in range(n):
            c |= ((b >> i) & 1) << pi[i]
        matrix[c, b] = 1.0
    return matrix


def cycles(pi: list[int]) -> list[list[int]]:
    seen: set[int] = set()
    out: list[list[int]] = []
    for start in range(len(pi)):
        if start in seen:
            continue
        cycle, i = [], start
        while i not in seen:
            seen.add(i)
            cycle.append(i)
            i = pi[i]
        if len(cycle) > 1:
            out.append(cycle)
    return out


def swap_construction(pi: list[int]) -> QuantumCircuit:
    """For each cycle c0 -> c1 -> .. -> c_{k-1} -> c0 (pi(c_j) = c_{j+1}), swap
    (c_{k-2}, c_{k-1}), then (c_{k-3}, c_{k-2}), .. down to (c_0, c_1)."""
    circuit = QuantumCircuit(len(pi))
    for cycle in cycles(pi):
        for j in range(len(cycle) - 2, -1, -1):
            circuit.swap(cycle[j], cycle[j + 1])
    return circuit


def _cycle_type(pi: list[int]) -> tuple[int, ...]:
    return tuple(sorted(len(c) for c in cycles(pi)))


class QubitPermutations(Family):
    name = "qubit_permutation"
    oracle_kind = "unitary"
    closed_form = True

    def variations(self) -> list[Variation]:
        rng = random.Random("qubit_permutation-v1")
        chosen: list[list[int]] = []
        # n = 3: every non-identity permutation (3 transpositions, 2 three-cycles).
        chosen += [list(p) for p in itertools.permutations(range(3)) if list(p) != [0, 1, 2]]
        # n = 4: stratified by cycle type so the 15 are not all transpositions.
        by_type: dict[tuple[int, ...], list[list[int]]] = {}
        for p in itertools.permutations(range(4)):
            if list(p) != [0, 1, 2, 3]:
                by_type.setdefault(_cycle_type(list(p)), []).append(list(p))
        for kind, count in (((2,), 4), ((3,), 4), ((4,), 4), ((2, 2), 3)):
            pool = sorted(by_type[kind])
            rng.shuffle(pool)
            chosen += pool[:count]
        return [Variation(self.name, i, {"n": len(pi), "pi": pi}) for i, pi in enumerate(chosen)]

    def statement(self, v: Variation) -> str:
        n, pi = v.params["n"], v.params["pi"]
        moves = ", ".join(f"qubit {i} -> qubit {pi[i]}" for i in range(n))
        return (
            f"Build a {n}-qubit Qiskit circuit that permutes the qubits so that the state "
            f"held on each qubit i ends up on qubit pi(i), where pi is: {moves}. Use "
            f"Qiskit's qubit numbering (qubit 0 is the least significant bit). The circuit's "
            f"unitary must be exactly this qubit permutation, up to global phase. No "
            f"measurement."
        )

    def verify(self, v: Variation) -> Verification:
        pi = v.params["pi"]
        oracle = permutation_unitary(pi)
        built = circuit_unitary(swap_construction(pi))
        result = unitaries_equal(oracle, built)
        return Verification(
            v, [Check("swap_construction_vs_definition", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        if circuit.num_qubits != v.params["n"]:
            return Check("strict_unitary", False, float("inf"), "wrong qubit count")
        result = unitaries_equal(permutation_unitary(v.params["pi"]), circuit_unitary(circuit))
        return Check("strict_unitary", result.equal, result.max_abs_diff)
