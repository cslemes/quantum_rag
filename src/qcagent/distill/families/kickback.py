"""Family K: Bernstein-Vazirani and Deutsch-Jozsa with a linear oracle (statevector).

Register: n input qubits 0..n-1 and one ancilla, qubit n. Oracle f(x) = s.x (mod 2) XOR c, s != 0.
Closed form (the oracle): the full algorithm (ancilla X then H, H on inputs, oracle, H on inputs)
ends in |s> on the inputs and |-> on the ancilla, up to global phase:
    psi(b) = [b_0..b_{n-1} == s] * (-1)^{b_n} / sqrt 2,   index k = sum_i b_i 2^i.
Construction: the circuit itself, CX(i, ancilla) for each set bit of s, X on the ancilla if c = 1.
"""

from __future__ import annotations

import random

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_state, states_equal


def kickback_state(n: int, s: int) -> np.ndarray:
    psi = np.zeros(1 << (n + 1), dtype=complex)
    psi[s] = 1 / np.sqrt(2)
    psi[s | (1 << n)] = -1 / np.sqrt(2)
    return psi


def kickback_circuit(n: int, s: int, c: int) -> QuantumCircuit:
    circuit = QuantumCircuit(n + 1)
    circuit.x(n)
    circuit.h(range(n + 1))
    for i in range(n):
        if (s >> i) & 1:
            circuit.cx(i, n)
    if c:
        circuit.x(n)
    circuit.h(range(n))
    return circuit


def _secret(s: int, n: int) -> str:
    return format(s, f"0{n}b")  # the integer's binary, qubit n-1 leftmost


class KickbackBvDj(Family):
    name = "kickback_bv_dj"
    oracle_kind = "statevector"
    closed_form = True

    N_RANGE = range(2, 9)

    def variations(self, count: int = 20) -> list[Variation]:
        rng = random.Random("kickback_bv_dj-v1")
        pool = []
        for n in self.N_RANGE:
            for s in range(1, 1 << n):
                pool.append(("bv", n, s, 0))
                pool.append(("dj", n, s, 0))
                pool.append(("dj", n, s, 1))
        rng.shuffle(pool)
        by_n: dict[int, list[tuple]] = {}
        for item in pool:
            by_n.setdefault(item[1], []).append(item)
        chosen: list[tuple] = []
        sizes = sorted(by_n)
        while len(chosen) < count:
            progressed = False
            for n in sizes:
                if by_n[n] and len(chosen) < count:
                    chosen.append(by_n[n].pop())
                    progressed = True
            if not progressed:
                raise ValueError(f"only {len(chosen)} variations exist, {count} requested")
        return [
            Variation(self.name, i, {"kind": k, "n": n, "s": s, "c": c})
            for i, (k, n, s, c) in enumerate(chosen)
        ]

    def statement(self, v: Variation) -> str:
        kind, n, s, c = (v.params[k] for k in ("kind", "n", "s", "c"))
        bits = _secret(s, n)
        common = (
            f"Use {n} input qubits (qubits 0 to {n - 1}) and one ancilla qubit (qubit {n}), "
            f"{n + 1} qubits in all. Qiskit's numbering applies: qubit 0 is the least "
            f"significant bit. Prepare the ancilla in |-> (X then H), put the input qubits in "
            f"uniform superposition, apply the oracle as a phase kickback onto the ancilla, "
            f"apply a Hadamard to every input qubit, and do not measure. The final state of "
            f"the whole register must match exactly, up to global phase."
        )
        if kind == "bv":
            return (
                f"Build the Bernstein-Vazirani circuit for the secret string s = {bits} "
                f"(s as an integer is {s}; qubit i holds bit i of s), whose oracle computes "
                f"f(x) = s.x mod 2. " + common
            )
        xor = " XOR 1" if c else ""
        return (
            f"Build the Deutsch-Jozsa circuit for the balanced oracle f(x) = s.x mod 2{xor}, "
            f"with s = {bits} (s as an integer is {s}; qubit i holds bit i of s). " + common
        )

    def verify(self, v: Variation) -> Verification:
        p = v.params
        result = states_equal(
            kickback_state(p["n"], p["s"]),
            circuit_state(kickback_circuit(p["n"], p["s"], p["c"])),
        )
        return Verification(
            v, [Check("algorithm_circuit_vs_final_state", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        p = v.params
        if circuit.num_qubits != p["n"] + 1:
            return Check("strict_state", False, float("inf"), "wrong qubit count")
        result = states_equal(kickback_state(p["n"], p["s"]), circuit_state(circuit))
        return Check("strict_state", result.equal, result.max_abs_diff)
