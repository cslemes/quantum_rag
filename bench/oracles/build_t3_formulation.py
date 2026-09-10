"""Builds the reference (oracle) circuits for the 12 T3 canonical tasks
(T046, T049) and serializes each to `bench/oracles/<task_id>.qpy`.

    uv run python -m bench.oracles.build_t3_formulation

T3 = "formulation": translating a stated cost function / Hamiltonian /
QUBO into the circuit that applies it as a diagonal phase
exp(-i*gamma*H)|+>^n. All 12 tasks use `oracle_kind="unitary"` — every
Hamiltonian here is diagonal in the computational basis (Z-only terms), so
the resulting unitary is well-defined on every one of the 2^n inputs
regardless of which one a test happens to start from, the same reasoning
that keeps QFT `unitary` (D3c) — and unlike D3d's reversible-arithmetic
finding, there is no ancilla/flatness concern at all here: every qubit is a
real problem variable, none are zero-initialized scratch registers, so
there is no "non-physical subspace" for the full-domain unitary check to be
over-constrained against.

Per D3e's "widest space of correct answers" warning for formulation tasks,
every family below fixes ALL numeric structure (graph weights, Hamiltonian
coefficients, QUBO matrix entries, gamma) exactly in the task's prompt —
never left to be optimized or chosen. See research.md D3f for a genuinely
NEW undeclared-constraint case found while designing family D: the QUBO ->
Ising substitution x_i = (1-z_i)/2 vs. x_i = (1+z_i)/2 are BOTH standard
conventions in the literature and produce Hamiltonians of OPPOSITE sign —
left unstated, a model using the other valid convention would be graded
wrong for an equally correct answer. Each D-family prompt states the exact
substitution used.

Four families, three qubit-count variants each:
  - A: weighted MaxCut-style Ising (pairwise Z_i Z_j only, non-uniform
    weights — T2's QAOA only ever used uniform-weight edges).
  - B: multi-body (3- and 4-qubit) Pauli-Z string interactions — a gate
    pattern (a CNOT ladder of arbitrary length, not just 2 CNOTs) that
    never appeared in T1 or T2.
  - C: combined single-qubit field terms (plain RZ) and pairwise coupling
    terms in one Hamiltonian — tests correctly combining two different
    term "shapes" in the same circuit.
  - D: QUBO matrix -> Ising Hamiltonian via an explicitly stated
    substitution, then the same phase-circuit construction as A/C.

Primary construction per term shape:
  - field term h_i Z_i: `RZ(2*gamma*h_i, i)`.
  - k-body term J * Z_{q1}...Z_{qk}: CNOT ladder down the chain, RZ(2*gamma*J)
    on the last qubit, CNOT ladder back up — verified (not assumed) against
    an independent Diagonal-based construction for k in {2,3,4} before use.
"""

from pathlib import Path

from qiskit import QuantumCircuit, qpy

OUT_DIR = Path(__file__).parent


def _zstring_term(qc: QuantumCircuit, qubits: list[int], gamma: float, coeff: float) -> None:
    """Applies exp(-i*gamma*coeff*Z_{q1}...Z_{qk}) via a CNOT ladder + RZ."""
    for i in range(len(qubits) - 1):
        qc.cx(qubits[i], qubits[i + 1])
    qc.rz(2 * gamma * coeff, qubits[-1])
    for i in reversed(range(len(qubits) - 1)):
        qc.cx(qubits[i], qubits[i + 1])


def _field_term(qc: QuantumCircuit, qubit: int, gamma: float, coeff: float) -> None:
    qc.rz(2 * gamma * coeff, qubit)


def weighted_ising(n: int, edges: dict[tuple[int, int], float], gamma: float) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for (i, j), weight in edges.items():
        _zstring_term(qc, [i, j], gamma, weight)
    return qc


def zstring_hamiltonian(
    n: int, terms: list[tuple[list[int], float]], gamma: float
) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for qubits, coeff in terms:
        _zstring_term(qc, qubits, gamma, coeff)
    return qc


def field_and_coupling(
    n: int,
    fields: dict[int, float],
    couplings: dict[tuple[int, int], float],
    gamma: float,
) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for qubit, h in fields.items():
        _field_term(qc, qubit, gamma, h)
    for (i, j), coupling in couplings.items():
        _zstring_term(qc, [i, j], gamma, coupling)
    return qc


def ising_from_qubo(
    qubo: list[list[float]], n: int
) -> tuple[dict[int, float], dict[tuple[int, int], float]]:
    """Substitution x_i = (1 - z_i)/2 applied to
    C(x) = sum_i Q_ii*x_i + sum_{i<j} Q_ij*x_i*x_j (Q given upper-triangular
    including the diagonal) — verified against brute-force enumeration of
    every bitstring for n=3 before being trusted (see session record); the
    additive constant is dropped (global phase only, per FR-004/Operator.
    equiv()'s own global-phase tolerance).
    """
    h: dict[int, float] = dict.fromkeys(range(n), 0.0)
    coupling: dict[tuple[int, int], float] = {}
    for i in range(n):
        h[i] += -qubo[i][i] / 2
    for i in range(n):
        for j in range(i + 1, n):
            qij = qubo[i][j]
            if qij == 0:
                continue
            h[i] += -qij / 4
            h[j] += -qij / 4
            coupling[(i, j)] = qij / 4
    return h, coupling


# task_id -> circuit
TASKS: dict[str, QuantumCircuit] = {
    # Family A: weighted MaxCut-style Ising (pairwise only, weighted edges)
    "ising_weighted_maxcut_3q": weighted_ising(3, {(0, 1): 0.6, (1, 2): -0.4, (0, 2): 0.9}, 0.5),
    "ising_weighted_maxcut_4q": weighted_ising(
        4, {(0, 1): 0.3, (1, 2): 0.7, (2, 3): -0.5, (0, 3): 0.4}, 0.45
    ),
    "ising_weighted_maxcut_5q": weighted_ising(
        5, {(0, 1): 0.5, (0, 2): -0.3, (0, 3): 0.8, (0, 4): 0.2}, 0.4
    ),
    # Family B: multi-body Z-string interactions
    "ising_zzz_3q": zstring_hamiltonian(3, [([0, 1, 2], 0.7)], 0.6),
    "ising_zzzz_4q": zstring_hamiltonian(4, [([0, 1, 2, 3], 0.5)], 0.5),
    "ising_mixed_body_4q": zstring_hamiltonian(4, [([0, 1], 0.4), ([1, 2, 3], 0.6)], 0.5),
    # Family C: field + pairwise coupling combined
    "ising_field_coupling_3q": field_and_coupling(3, {0: 0.3, 1: 0.5, 2: -0.2}, {(0, 1): 0.4}, 0.5),
    "ising_field_coupling_4q": field_and_coupling(
        4,
        {0: 0.2, 1: -0.4, 2: 0.3, 3: 0.1},
        {(0, 1): 0.5, (2, 3): 0.3},
        0.45,
    ),
    "ising_field_coupling_5q": field_and_coupling(
        5,
        {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3},
        {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5},
        0.4,
    ),
    # Family D: QUBO -> Ising (explicit substitution) -> phase circuit
    "qubo_ising_3var": field_and_coupling(
        3, *ising_from_qubo([[2, -1, 0.5], [0, -3, 1.5], [0, 0, 1]], 3), 0.5
    ),
    "qubo_ising_4var": field_and_coupling(
        4,
        *ising_from_qubo(
            [[1.5, -0.8, 0.6, 0.0], [0, -2.0, 0.4, 0.9], [0, 0, 1.0, -0.7], [0, 0, 0, 0.5]], 4
        ),
        0.45,
    ),
    "qubo_ising_5var": field_and_coupling(
        5,
        *ising_from_qubo(
            [
                [1.0, 0.5, -0.6, 0.0, 0.3],
                [0, -1.5, 0.8, -0.4, 0.0],
                [0, 0, 1.2, 0.5, -0.3],
                [0, 0, 0, -0.8, 0.6],
                [0, 0, 0, 0, 0.4],
            ],
            5,
        ),
        0.4,
    ),
}


def main() -> None:
    for task_id, circuit in TASKS.items():
        path = OUT_DIR / f"{task_id}.qpy"
        with open(path, "wb") as f:
            qpy.dump(circuit, f)
        print(f"wrote {path} ({circuit.num_qubits} qubits)")


if __name__ == "__main__":
    main()
