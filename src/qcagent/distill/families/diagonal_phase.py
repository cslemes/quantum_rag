"""Family H: diagonal Ising-phase circuits (statevector).

Closed form (the oracle): H is a sum of Z-strings, H = sum_k c_k prod_{i in S_k} Z_i. Starting from
H^(x)n |0...0> and applying exp(-i H), the output state is
    2^(-n/2) sum_x exp(-i E(x)) |x>,   E(x) = sum_k c_k prod_{i in S_k} (-1)^{x_i},
index k = sum_i x_i 2^i. Written entry by entry from the energy table.
Construction (shares no code with it): per term, a CX parity ladder onto the last qubit of the
string, RZ(2 c_k), and the ladder undone.
"""

from __future__ import annotations

import random

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_state, states_equal

COEFF_GRID = [s * v for v in (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0) for s in (1, -1)]


def _fmt(c: float) -> str:
    return f"{c:g}"


def diagonal_state(n: int, terms: list[list[int]], coeffs: list[float]) -> np.ndarray:
    amplitudes = np.empty(1 << n, dtype=complex)
    for x in range(1 << n):
        energy = 0.0
        for subset, c in zip(terms, coeffs, strict=True):
            sign = 1
            for i in subset:
                sign *= -1 if (x >> i) & 1 else 1
            energy += c * sign
        amplitudes[x] = np.exp(-1j * energy)
    return amplitudes / np.sqrt(1 << n)


def ladder_circuit(n: int, terms: list[list[int]], coeffs: list[float]) -> QuantumCircuit:
    circuit = QuantumCircuit(n)
    circuit.h(range(n))
    for subset, c in zip(terms, coeffs, strict=True):
        last = subset[-1]
        for i in subset[:-1]:
            circuit.cx(i, last)
        circuit.rz(2 * c, last)
        for i in reversed(subset[:-1]):
            circuit.cx(i, last)
    return circuit


class DiagonalPhase(Family):
    name = "diagonal_phase_ising"
    oracle_kind = "statevector"
    closed_form = True

    N_RANGE = range(3, 7)

    def variations(self, count: int = 20) -> list[Variation]:
        rng = random.Random("diagonal_phase_ising-v1")
        out: list[Variation] = []
        seen: set[str] = set()
        ns = list(self.N_RANGE)
        i = 0
        while len(out) < count:
            n = ns[i % len(ns)]
            i += 1
            n_terms = rng.randint(1, min(4, 2**n - 1))
            subsets: list[list[int]] = []
            while len(subsets) < n_terms:
                size = rng.randint(1, min(n, 4))
                s = sorted(rng.sample(range(n), size))
                if s not in subsets:
                    subsets.append(s)
            subsets.sort(key=lambda s: (len(s), s))
            coeffs = [rng.choice(COEFF_GRID) for _ in subsets]
            v = Variation(self.name, len(out), {"n": n, "terms": subsets, "coeffs": coeffs})
            if v.key in seen:
                continue
            seen.add(v.key)
            out.append(v)
        return out

    def statement(self, v: Variation) -> str:
        n, terms, coeffs = v.params["n"], v.params["terms"], v.params["coeffs"]

        def term(s: list[int], c: float) -> str:
            return f"({_fmt(c)}) * " + "*".join(f"Z_{i}" for i in s)

        h = " + ".join(term(s, c) for s, c in zip(terms, coeffs, strict=True))
        return (
            f"Build a {n}-qubit Qiskit circuit that starts from |0...0>, applies a Hadamard to "
            f"every qubit, and then applies the diagonal evolution exp(-i H) with "
            f"H = {h}, where Z_i is the Pauli Z on qubit i. The output state must be "
            f"2^(-{n}/2) * sum over x of exp(-i E(x)) |x>, where E(x) is H evaluated with Z_i = "
            f"(-1)^(x_i). Use Qiskit's qubit numbering (qubit 0 is the least significant bit). "
            f"The state must match exactly, up to global phase. No measurement."
        )

    def verify(self, v: Variation) -> Verification:
        p = v.params
        result = states_equal(
            diagonal_state(p["n"], p["terms"], p["coeffs"]),
            circuit_state(ladder_circuit(p["n"], p["terms"], p["coeffs"])),
        )
        return Verification(
            v, [Check("parity_ladder_vs_energy_table", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        p = v.params
        if circuit.num_qubits != p["n"]:
            return Check("strict_state", False, float("inf"), "wrong qubit count")
        result = states_equal(
            diagonal_state(p["n"], p["terms"], p["coeffs"]), circuit_state(circuit)
        )
        return Check("strict_state", result.equal, result.max_abs_diff)

    def calibrate(self) -> list[Check]:
        """Limit cases written out by hand: one Z, and one ZZ parity table."""
        got = diagonal_state(1, [[0]], [0.5])
        want = np.array([np.exp(-0.5j), np.exp(0.5j)]) / np.sqrt(2)
        zz = diagonal_state(2, [[0, 1]], [1.0])
        zz_want = np.exp(-1j * np.array([1, -1, -1, 1])) / 2
        return [
            Check("single_z", states_equal(got, want).equal),
            Check("zz_parity_table", states_equal(zz, zz_want).equal),
        ]
