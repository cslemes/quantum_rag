"""Builds the reference (oracle) circuits for the 12 T4 canonical tasks
(T047, T049) and serializes each to `bench/oracles/<task_id>.qpy`.

    uv run python -m bench.oracles.build_t4_hardware

T4 = "hardware-constrained": every task sets `coupling_map="linear_5"`
(`bench/tasks/t4_hardware/*.json`), the only real non-trivial topology
`COUPLING_MAPS` defines (`resource.py`'s own comment already flags
`heavy_hex_27` as unimplemented — a real device's edge list, not a formula
— and this module does not add one; not fabricated, left as a genuine gap,
same discipline as D3e-3's VQE H2 sourcing and D3d's teleportation flag).
All 12 tasks are therefore n_qubits=5, the fixed size `linear_5` defines.

**IMPORTANT — `oracle_kind="resource"` was checked and does not exist as a
dispatch value anywhere in the runtime** (`grep` over `src/qcagent/graph.py`
confirms `make_semantic_check_node` only branches on `StatePreparationOracle
| QuantumCircuit | dict | tuple` — no "resource" branch was ever built).
This is not a gap T4 needs to fill: `resource_check` is ALREADY orthogonal
to `oracle_kind` in the existing pipeline — it only needs a reference
`QuantumCircuit` (which `oracle_kind="statevector"`/`"unitary"` both
already provide) and runs automatically once `semantic_check` sets
`verification_method` (D3c). Every T4 task below uses the SAME functional
`oracle_kind` as its family would use in T1-T3 (`statevector` for GHZ,
`unitary` for the Ising/Z-string families) — what makes a task "T4" is
`coupling_map="linear_5"`, not a different `oracle_kind`. See research.md
D3h for the full record of this finding.

**Reference-depth methodology (asked for explicitly, research.md D3h)**:
the reference circuit for every task here is the SAME KIND of "obvious,
not hand-tuned" construction used throughout T1-T3 — never a topology
hand-picked to be optimal for `linear_5`. `check_resources`'s pass
criterion is `depth_ratio <= max_depth_ratio` (an upper bound, not
equality) — a generated circuit that routes BETTER than this reference
(e.g. a model that recognizes a chain topology is cheaper than a star on a
line) gets `depth_ratio < 1.0`, which always satisfies the upper bound.
That inequality direction is what makes "the reference might not be
optimal" safe rather than a source of false rejections: only a circuit
meaningfully WORSE than a straightforward implementation can fail. Both
generated and reference are transpiled with IDENTICAL `coupling_map`,
`optimization_level` (module-wide default `opt_level=2`, `resource.py`'s
own existing default — used unchanged here, not cherry-picked for T4), and
`seed_transpiler` (`check_resources`'s existing default, `seed=42`) —
FR-006's symmetric-transpilation requirement, already correctly implemented
before this tier existed (contracts/validators.md TRAP 3) and reconfirmed,
not modified, here.

Families (qubit SUBSET/EDGE locality deliberately varies within each family
— from fully adjacent on the line to maximally scattered — so the tier
actually exercises routing, rather than all 12 tasks trivially fitting a
contiguous sub-chain):
  - A: GHZ over a qubit SUBSET of the 5-qubit line (`statevector`) — other
    qubits stay at |0>. Reuses D3c's reasoning (state-prep from |0...0>,
    unitarily-inequivalent topologies must both be accepted).
  - B: weighted 2-body Ising phase circuit (`unitary`, D3f's construction)
    with varying edge locality.
  - C: multi-body Z-string terms (`unitary`, D3d/D3f's CNOT-ladder pattern)
    over scattered vs. adjacent qubit lists.
  - D: field + coupling combined (`unitary`, D3f's construction) with
    scattered vs. local coupling terms.
"""

from pathlib import Path

from qiskit import QuantumCircuit, qpy

OUT_DIR = Path(__file__).parent
N_QUBITS = 5  # fixed — matches linear_5's size


def ghz_over_subset(subset: list[int]) -> QuantumCircuit:
    """GHZ over `subset` qubits, |0> on every other qubit — a plain H + CX
    chain THROUGH THE SUBSET (in the given order), not `StatePreparation`.

    T1 used `StatePreparation` as GHZ's primary specifically because it
    carries zero hand-derivation risk (D3c) — a property that matters for a
    FUNCTIONAL-correctness-focused tier. T4 is resource-focused: the
    reference circuit's OWN transpiled depth is now the thing being
    compared against, and `StatePreparation`'s generic synthesis is far
    deeper than any reasonable hand-written GHZ circuit (measured: 57 vs 5
    for the 5-qubit case after transpiling onto linear_5) — using it here
    would make `depth_ratio` reward almost ANY reasonable model answer
    trivially, not because the model did anything hardware-aware, but
    because the reference itself was needlessly bloated. The chain
    construction is exactly as well-established/low-risk as T1's judged
    `StatePreparation` to be (H + CX is the textbook GHZ circuit), so this
    is not a return to T1's original hand-derivation risk — see D3h,
    research.md, for why resource-focused tasks need this reference-choice
    care that functional-only tasks (T1-T3) did not.
    """
    qc = QuantumCircuit(N_QUBITS)
    ordered = list(subset)
    qc.h(ordered[0])
    for i in range(len(ordered) - 1):
        qc.cx(ordered[i], ordered[i + 1])
    return qc


def _zstring_term(qc: QuantumCircuit, qubits: list[int], gamma: float, coeff: float) -> None:
    for i in range(len(qubits) - 1):
        qc.cx(qubits[i], qubits[i + 1])
    qc.rz(2 * gamma * coeff, qubits[-1])
    for i in reversed(range(len(qubits) - 1)):
        qc.cx(qubits[i], qubits[i + 1])


def weighted_ising(edges: dict[tuple[int, int], float], gamma: float) -> QuantumCircuit:
    qc = QuantumCircuit(N_QUBITS)
    qc.h(range(N_QUBITS))
    for (i, j), weight in edges.items():
        _zstring_term(qc, [i, j], gamma, weight)
    return qc


def zstring_hamiltonian(terms: list[tuple[list[int], float]], gamma: float) -> QuantumCircuit:
    qc = QuantumCircuit(N_QUBITS)
    qc.h(range(N_QUBITS))
    for qubits, coeff in terms:
        _zstring_term(qc, qubits, gamma, coeff)
    return qc


def field_and_coupling(
    fields: dict[int, float], couplings: dict[tuple[int, int], float], gamma: float
) -> QuantumCircuit:
    qc = QuantumCircuit(N_QUBITS)
    qc.h(range(N_QUBITS))
    for qubit, h in fields.items():
        qc.rz(2 * gamma * h, qubit)
    for (i, j), coupling in couplings.items():
        _zstring_term(qc, [i, j], gamma, coupling)
    return qc


# task_id -> circuit
TASKS: dict[str, QuantumCircuit] = {
    # Family A: GHZ over a qubit subset of linear_5 (statevector)
    "ghz_linear5_full": ghz_over_subset([0, 1, 2, 3, 4]),  # adjacent chain exists
    "ghz_linear5_scattered_even": ghz_over_subset([0, 2, 4]),  # distance-2 hops
    "ghz_linear5_mixed": ghz_over_subset([0, 1, 4]),  # one adjacent, one far
    "ghz_linear5_endpoints": ghz_over_subset([0, 4]),  # maximum distance, single pair
    # Family B: weighted 2-body Ising, varying edge locality (unitary)
    "ising_linear5_local": weighted_ising(
        {(0, 1): 0.4, (1, 2): -0.3, (2, 3): 0.5, (3, 4): -0.2}, 0.5
    ),
    "ising_linear5_distance2": weighted_ising({(0, 2): 0.5, (1, 3): -0.4, (2, 4): 0.3}, 0.45),
    "ising_linear5_endpoints": weighted_ising({(0, 4): 0.6}, 0.5),
    "ising_linear5_mixed": weighted_ising({(0, 1): 0.3, (2, 3): -0.4, (0, 4): 0.5}, 0.45),
    # Family C: multi-body Z-string, scattered vs. adjacent (unitary)
    "zstring_linear5_scattered": zstring_hamiltonian([([0, 2, 4], 0.6)], 0.5),
    "zstring_linear5_full_chain": zstring_hamiltonian([([0, 1, 2, 3, 4], 0.5)], 0.5),
    # Family D: field + coupling, scattered vs. local (unitary)
    "field_coupling_linear5_scattered": field_and_coupling(
        {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}, {(0, 4): 0.4, (1, 3): -0.3}, 0.4
    ),
    "field_coupling_linear5_local": field_and_coupling(
        {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3},
        {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5},
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
