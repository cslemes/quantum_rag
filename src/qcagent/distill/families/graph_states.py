"""Family 3: graph states (statevector).

Closed form (the oracle):
    |G> = 2^{-n/2} sum_x (-1)^{sum_{(i,j) in E} x_i x_j} |x>,  index k = sum x_i 2^i.
Construction: H on every qubit, CZ on every edge.

Selection: connected graphs on 4 and 5 vertices, and any graph in the
local-Clifford class of the GHZ state is excluded. The class is ENUMERATED, by
breadth-first search under local complementation (Van den Nest et al.: two
graph states are local-Clifford equivalent iff their graphs are related by a
sequence of local complementations), not assumed to be "the star and the
complete graph". Disconnected graphs are not used: a component that is a pair
or a 3-vertex path is itself GHZ-class.
"""

from __future__ import annotations

import itertools
import random
from collections import deque

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families.base import Check, Family, Variation, Verification
from qcagent.distill.strict import circuit_state, states_equal

Edges = tuple[tuple[int, int], ...]


def _adjacency(n: int, edges: Edges) -> list[list[int]]:
    adj = [[0] * n for _ in range(n)]
    for i, j in edges:
        adj[i][j] = adj[j][i] = 1
    return adj


def _edges(adj: list[list[int]]) -> Edges:
    n = len(adj)
    return tuple((i, j) for i in range(n) for j in range(i + 1, n) if adj[i][j])


def _connected(n: int, edges: Edges) -> bool:
    adj = _adjacency(n, edges)
    seen, queue = {0}, deque([0])
    while queue:
        u = queue.popleft()
        for w in range(n):
            if adj[u][w] and w not in seen:
                seen.add(w)
                queue.append(w)
    return len(seen) == n


def local_complement(edges: Edges, v: int, n: int) -> Edges:
    adj = _adjacency(n, edges)
    neighbours = [u for u in range(n) if adj[v][u]]
    for i, j in itertools.combinations(neighbours, 2):
        adj[i][j] = adj[j][i] = 1 - adj[i][j]
    return _edges(adj)


def lc_orbit(edges: Edges, n: int) -> set[Edges]:
    seen = {edges}
    queue = deque([edges])
    while queue:
        current = queue.popleft()
        for v in range(n):
            nxt = local_complement(current, v, n)
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def star(n: int) -> Edges:
    return tuple((0, j) for j in range(1, n))


def connected_graphs(n: int) -> list[Edges]:
    pairs = list(itertools.combinations(range(n), 2))
    graphs = []
    for mask in range(1 << len(pairs)):
        edges = tuple(p for k, p in enumerate(pairs) if mask >> k & 1)
        if _connected(n, edges):
            graphs.append(edges)
    return graphs


def ghz_class(n: int) -> set[Edges]:
    return lc_orbit(star(n), n)


def _iso_class(n: int, edges: Edges) -> Edges:
    """Canonical form under vertex relabelling: the smallest relabelled edge tuple."""
    best = None
    for perm in itertools.permutations(range(n)):
        relabelled = tuple(sorted(tuple(sorted((perm[i], perm[j]))) for i, j in edges))
        if best is None or relabelled < best:
            best = relabelled
    assert best is not None
    return best


def graph_state_vector(n: int, edges: Edges) -> np.ndarray:
    """The oracle, from the amplitude formula."""
    amplitudes = np.empty(1 << n, dtype=complex)
    for k in range(1 << n):
        exponent = sum(((k >> i) & 1) * ((k >> j) & 1) for i, j in edges)
        amplitudes[k] = (-1) ** exponent
    return amplitudes / np.sqrt(1 << n)


def graph_state_circuit(n: int, edges: Edges) -> QuantumCircuit:
    circuit = QuantumCircuit(n)
    circuit.h(range(n))
    for i, j in edges:
        circuit.cz(i, j)
    return circuit


class GraphStates(Family):
    name = "graph_state"
    oracle_kind = "statevector"
    closed_form = True

    def variations(self) -> list[Variation]:
        rng = random.Random("graph_state-v1")
        chosen: list[tuple[int, Edges]] = []
        for n in (4, 5):
            excluded = ghz_class(n)
            usable = [g for g in connected_graphs(n) if g not in excluded]
            by_class: dict[Edges, list[Edges]] = {}
            for g in usable:
                by_class.setdefault(_iso_class(n, g), []).append(g)
            classes = sorted(by_class)
            rng.shuffle(classes)
            for members in by_class.values():
                members.sort()
                rng.shuffle(members)
            picked: list[Edges] = []
            while len(picked) < 10:  # round-robin over isomorphism classes
                for c in classes:
                    if by_class[c] and len(picked) < 10:
                        picked.append(by_class[c].pop())
            chosen += [(n, g) for g in picked]
        return [
            Variation(self.name, i, {"n": n, "edges": [list(e) for e in g]})
            for i, (n, g) in enumerate(chosen)
        ]

    def statement(self, v: Variation) -> str:
        n = v.params["n"]
        edges = ", ".join(f"({i}, {j})" for i, j in v.params["edges"])
        return (
            f"Prepare the graph state of the graph with {n} vertices (vertex i is qubit i) and "
            f"edges {edges}: the state 2^(-{n}/2) * sum over x of (-1)^(sum over edges (i, j) of "
            f"x_i x_j) |x>, where x_i is the value of qubit i. Use Qiskit's qubit numbering "
            f"(qubit 0 is the least significant bit) and start from |0...0>. The output state "
            f"must match exactly, up to global phase. No measurement."
        )

    def verify(self, v: Variation) -> Verification:
        n = v.params["n"]
        edges: Edges = tuple(tuple(e) for e in v.params["edges"])  # type: ignore[arg-type]
        result = states_equal(
            graph_state_vector(n, edges), circuit_state(graph_state_circuit(n, edges))
        )
        outside_ghz = Check(
            "outside_ghz_lc_class", edges not in ghz_class(n), detail="graph is in GHZ's class"
        )
        connected = Check("connected", _connected(n, edges), detail="graph is disconnected")
        return Verification(
            v,
            [
                Check("h_cz_construction_vs_closed_form", result.equal, result.max_abs_diff),
                outside_ghz,
                connected,
            ],
        )

    def accepts(self, v: Variation, circuit: QuantumCircuit) -> Check:
        n = v.params["n"]
        edges: Edges = tuple(tuple(e) for e in v.params["edges"])  # type: ignore[arg-type]
        if circuit.num_qubits != n:
            return Check("strict_state", False, float("inf"), "wrong qubit count")
        result = states_equal(graph_state_vector(n, edges), circuit_state(circuit))
        return Check("strict_state", result.equal, result.max_abs_diff)
