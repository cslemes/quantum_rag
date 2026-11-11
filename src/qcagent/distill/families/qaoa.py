"""Family P: QAOA with p = 1 on a MaxCut graph (statevector), two independent constructions.

State: |psi> = exp(-i beta sum_i X_i) exp(-i gamma sum_{(i,j) in E} Z_i Z_j) H^(x)n |0...0>.
A: CX - RZ(2 gamma) - CX per edge, then RX(2 beta) on every qubit (gates).
B: the cost layer as a diagonal phase vector over the cut table, the mixer as a tensor contraction
   of the 2x2 matrix cos(beta) I - i sin(beta) X (linear algebra, no circuit).
They must agree exactly before the family is used; B is the oracle for candidates.
"""

from __future__ import annotations

import functools
import random

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.families.graph_states import connected_graphs
from qcagent.distill.strict import circuit_state, states_equal

GRID = [round(0.1 * k, 1) for k in range(1, 11)]


@functools.cache
def _graphs(n: int):
    return connected_graphs(n)


def qaoa_gates(n: int, edges: list[list[int]], gamma: float, beta: float) -> QuantumCircuit:
    circuit = QuantumCircuit(n)
    circuit.h(range(n))
    for i, j in edges:
        circuit.cx(i, j)
        circuit.rz(2 * gamma, j)
        circuit.cx(i, j)
    for q in range(n):
        circuit.rx(2 * beta, q)
    return circuit


def qaoa_linear_algebra(n: int, edges: list[list[int]], gamma: float, beta: float) -> np.ndarray:
    state = np.full(1 << n, 1 / np.sqrt(1 << n), dtype=complex)
    for x in range(1 << n):
        energy = sum(1 if ((x >> i) & 1) == ((x >> j) & 1) else -1 for i, j in edges)
        state[x] *= np.exp(-1j * gamma * energy)
    mixer = np.array(
        [[np.cos(beta), -1j * np.sin(beta)], [-1j * np.sin(beta), np.cos(beta)]], dtype=complex
    )
    tensor = state.reshape([2] * n)  # every axis gets the same 2x2, so axis order does not matter
    for axis in range(n):
        tensor = np.moveaxis(np.tensordot(mixer, tensor, axes=([1], [axis])), 0, axis)
    return tensor.reshape(-1)


class QaoaP1(Family):
    name = "qaoa_p1"
    oracle_kind = "statevector"
    closed_form = False  # two independent constructions check each other

    N_RANGE = range(3, 7)

    def variations(self, count: int = 20) -> list[Variation]:
        rng = random.Random("qaoa_p1-v1")
        seen: set[str] = set()
        out: list[Variation] = []
        ns = list(self.N_RANGE)
        i = 0
        while len(out) < count:
            n = ns[i % len(ns)]
            i += 1
            edges = rng.choice(_graphs(n))
            gamma, beta = rng.choice(GRID), rng.choice(GRID)
            v = Variation(
                self.name,
                len(out),
                {"n": n, "edges": [list(e) for e in edges], "gamma": gamma, "beta": beta},
            )
            if v.key in seen:
                continue
            seen.add(v.key)
            out.append(v)
        return out

    def statement(self, v: Variation) -> str:
        p = v.params
        edges = ", ".join(f"({i}, {j})" for i, j in p["edges"])
        return (
            f"Build a one-layer (p = 1) QAOA circuit for MaxCut on the graph with {p['n']} "
            f"vertices (vertex i is qubit i) and edges {edges}. Start from |0...0>, apply a "
            f"Hadamard to every qubit, then the cost layer exp(-i*gamma*sum over edges (i, j) of "
            f"Z_i Z_j) with gamma = {p['gamma']}, then the mixer layer exp(-i*beta*sum over qubits "
            f"of X_i) with beta = {p['beta']} (an RX(2*beta) on each qubit). Use Qiskit's qubit "
            f"numbering. The output state must match exactly, up to global phase. No "
            f"measurement, no free Parameter objects."
        )

    def verify(self, v: Variation) -> Verification:
        p = v.params
        a = circuit_state(qaoa_gates(p["n"], p["edges"], p["gamma"], p["beta"]))
        b = qaoa_linear_algebra(p["n"], p["edges"], p["gamma"], p["beta"])
        result = states_equal(b, a)
        return Verification(
            v, [Check("gates_vs_diagonal_and_contraction", result.equal, result.max_abs_diff)]
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        p = v.params
        if circuit.num_qubits != p["n"]:
            return Check("strict_state", False, float("inf"), "wrong qubit count")
        result = states_equal(
            qaoa_linear_algebra(p["n"], p["edges"], p["gamma"], p["beta"]), circuit_state(circuit)
        )
        return Check("strict_state", result.equal, result.max_abs_diff)

    def calibrate(self) -> list[Check]:
        """beta = 0 leaves the cost layer on |+>^n; gamma = 0 leaves a pure RX layer."""
        n, edges = 3, [[0, 1], [1, 2]]
        a = circuit_state(qaoa_gates(n, edges, 0.4, 0.0))
        b = qaoa_linear_algebra(n, edges, 0.4, 0.0)
        c = circuit_state(qaoa_gates(n, edges, 0.0, 0.3))
        d = qaoa_linear_algebra(n, edges, 0.0, 0.3)
        return [
            Check("beta_zero", states_equal(b, a).equal),
            Check("gamma_zero", states_equal(d, c).equal),
        ]
