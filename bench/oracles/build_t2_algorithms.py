"""Builds the reference (oracle) circuits for T2 canonical tasks (T045,
T049) and serializes each to `bench/oracles/<task_id>.qpy`.

    uv run python -m bench.oracles.build_t2_algorithms

Principle V / FR-018: see build_t1_primitives.py's module docstring for the
independence discipline this follows (primary here, never imported by
`bench/validate_oracles.py`'s alternative constructions).

**15/18 T2 tasks, not 18/18** — VQE H2 (3 tasks) is NOT included. This
project has no chemistry backend (`qiskit-nature`/`pyscf` are not installed
in this environment) to compute a real H2 electronic-structure Hamiltonian,
and reciting molecular-orbital coefficients from memory as verified ground
truth for a benchmark oracle is exactly the kind of unverifiable claim
Principle V/FR-018 exists to rule out — a wrong sign or magnitude in a
memorized Hamiltonian would silently corrupt every VQE run against it, with
no way to catch it the way `Operator.equiv()` against an independent
construction catches a decomposition bug. Flagged, not guessed — see
research.md D3d's T045 entry. `oracle_kind="energy"` and `check_energy` are
already implemented and unaffected; this is a missing INPUT (real H2
coefficients), not a missing verification mechanism.

oracle_kind for all 15 tasks here is "statevector" — see research.md D3d's
T045 section for why: each family embeds ONE FIXED oracle/parameter set per
task (never variable-by-instance within a task), making the circuit's
output from |0...0> a single deterministic target, exactly like Bell/GHZ
(D3c). None of Simon, Bernstein-Vazirani, Grover (fixed marked item(s) and
iteration count), or QPE (exactly-representable phase, fixed eigenstate) is
`oracle_kind="unitary"` here — none of them is specified as a general
transform over arbitrary input; QAOA MaxCut is `oracle_kind="statevector"`
for the same reason once graph AND parameters (beta, gamma) are fully fixed
in the prompt (removing the classical-optimization freedom that would
otherwise make "the answer" ill-defined per task).

Ancilla / qubit-index conventions (same "state in the prompt, not just the
oracle" principle as D3c's DJ, D3d's flatness note):
  - Bernstein-Vazirani: ancilla is the highest-indexed qubit (qubit n),
    identical to T1's Deutsch-Jozsa convention.
  - Simon: input register is qubits 0..n-1, output register is qubits
    n..2n-1.
  - QPE: counting register is qubits 0..n_count-1, eigenstate register is
    the single highest-indexed qubit.
  - Grover, QAOA: no ancilla — all qubits are the "problem" register.
"""

from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import Diagonal

OUT_DIR = Path(__file__).parent


def bernstein_vazirani(n_input: int, secret: int) -> QuantumCircuit:
    """Identical structure to T1's Deutsch-Jozsa balanced oracle (ancilla at
    qubit n_input, bit-flip CNOTs from each "active" input qubit) — BV is
    the special case of a linear oracle where the goal is recovering the
    full secret, not just constant-vs-balanced.
    """
    qc = QuantumCircuit(n_input + 1)
    qc.x(n_input)
    qc.h(range(n_input + 1))
    for i in range(n_input):
        if (secret >> i) & 1:
            qc.cx(i, n_input)
    qc.h(range(n_input))
    return qc


def simon(n: int, secret: int) -> QuantumCircuit:
    """Standard 2-register Simon oracle. j = index of secret's lowest set
    bit. Output register: y_i = x_i XOR (s_i AND x_j) for every i — verified
    (not assumed) to satisfy f(x) = f(x XOR secret) for every x, by brute
    force over the full input space, before being trusted here.

    Input register is qubits 0..n-1, output register is qubits n..2n-1.
    """
    qc = QuantumCircuit(2 * n)
    j = (secret & -secret).bit_length() - 1
    qc.h(range(n))
    for i in range(n):
        qc.cx(i, n + i)
    for i in range(n):
        if (secret >> i) & 1:
            qc.cx(j, n + i)
    qc.h(range(n))
    return qc


def _diffuser(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(range(n))
    qc.x(range(n))
    qc.h(n - 1)
    qc.mcx(list(range(n - 1)), n - 1)
    qc.h(n - 1)
    qc.x(range(n))
    qc.h(range(n))
    return qc


def grover(n: int, marked: list[int], iterations: int) -> QuantumCircuit:
    """Pure PHASE oracle (no ancilla — `Diagonal` marks each index in
    `marked` with a -1 phase directly), stated explicitly in each task's
    prompt to remove the ancilla-vs-no-ancilla convention ambiguity a
    "build a Grover oracle" prompt would otherwise leave open. `iterations`
    and `marked` are fixed exactly by the task, not left to the model to
    choose or derive — with both pinned, the state after `iterations`
    applications of (oracle; diffuser) to |0...0> is a SINGLE well-defined
    target regardless of which internal diffuser gate decomposition reaches
    the same 2|s><s|-I unitary (there is no "many valid final states"
    ambiguity here, unlike D3c's GHZ case — the diffuser has one
    mathematical definition, only many equivalent decompositions of it).
    """
    diag: list[complex] = [1] * (2**n)
    for m in marked:
        diag[m] = -1
    oracle_circuit = QuantumCircuit(n)
    oracle_circuit.append(Diagonal(diag), range(n))

    qc = QuantumCircuit(n)
    qc.h(range(n))
    for _ in range(iterations):
        qc.compose(oracle_circuit, inplace=True)
        qc.compose(_diffuser(n), inplace=True)
    return qc


def qpe(n_count: int, k: int) -> QuantumCircuit:
    """Phase estimation of a PhaseGate P(2*pi*k/2^n_count) on eigenstate
    |1>, with k an INTEGER — chosen so the phase is exactly representable
    in n_count bits, which makes the circuit deterministic: the counting
    register lands EXACTLY on |k> (fidelity 1.0, not approximate) and the
    eigenstate register is unchanged (|1> throughout, by the definition of
    an eigenstate). Counting register: qubits 0..n_count-1 (ascending
    significance, qubit 0 lowest). Eigenstate register: qubit n_count.

    Inverse QFT below is written fresh for this module (high-to-low qubit
    index, control on the LOWER qubit) — the same direction T1's QFT
    (research.md D3d) confirmed correct against `qiskit.circuit.library.
    QFTGate`, re-derived independently here rather than imported, per this
    module's own independence discipline.
    """
    qc = QuantumCircuit(n_count + 1)
    qc.x(n_count)
    qc.h(range(n_count))
    for j in range(n_count):
        angle = 2 * np.pi * k / (2**n_count) * (2**j)
        qc.cp(angle, j, n_count)
    for i in range(n_count // 2):
        qc.swap(i, n_count - 1 - i)
    for j in range(n_count):
        for k2 in range(j):
            qc.cp(-np.pi / (2 ** (j - k2)), k2, j)
        qc.h(j)
    return qc


def qaoa_maxcut(n: int, edges: list[tuple[int, int]], gamma: float, beta: float) -> QuantumCircuit:
    """p=1 QAOA MaxCut ansatz, GRAPH and PARAMETERS (gamma, beta) both fully
    fixed by the task — removing the classical-optimization freedom that
    would otherwise leave "the answer" undefined (D3d): QAOA's angles are
    normally tuned to maximize cut expectation, so if the prompt only named
    the graph, any two models choosing different (but both reasonable)
    angles would legitimately reach different final states, and fixing ONE
    arbitrary choice as ground truth would reject the other. With angles
    pinned exactly, the circuit is a specific, deterministic transformation
    of |0...0>, same footing as every other family in this module. Cost
    interaction per edge (i,j) implemented as CX-RZ-CX (a standard exact
    decomposition of exp(-i*gamma*Z_i*Z_j) up to global phase); mixer as
    per-qubit RX(2*beta).
    """
    qc = QuantumCircuit(n)
    qc.h(range(n))
    for i, j in edges:
        qc.cx(i, j)
        qc.rz(2 * gamma, j)
        qc.cx(i, j)
    for q in range(n):
        qc.rx(2 * beta, q)
    return qc


# task_id -> circuit
TASKS: dict[str, QuantumCircuit] = {
    "bv_4q": bernstein_vazirani(3, 0b101),
    "bv_5q": bernstein_vazirani(4, 0b1011),
    "bv_6q": bernstein_vazirani(5, 0b10110),
    "simon_6q": simon(3, 0b101),
    "simon_8q": simon(4, 0b1010),
    "simon_10q": simon(5, 0b10110),
    "grover_3q": grover(3, [5], 2),
    "grover_4q": grover(4, [9], 3),
    "grover_5q": grover(5, [13, 20], 3),
    "qpe_4q": qpe(3, 3),
    "qpe_5q": qpe(4, 5),
    "qpe_6q": qpe(5, 11),
    "qaoa_maxcut_3q": qaoa_maxcut(3, [(0, 1), (1, 2), (0, 2)], 0.5, 0.3),
    "qaoa_maxcut_4q": qaoa_maxcut(4, [(0, 1), (1, 2), (2, 3), (3, 0)], 0.6, 0.4),
    "qaoa_maxcut_5q": qaoa_maxcut(5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)], 0.7, 0.35),
}


def main() -> None:
    for task_id, circuit in TASKS.items():
        path = OUT_DIR / f"{task_id}.qpy"
        with open(path, "wb") as f:
            qpy.dump(circuit, f)
        print(f"wrote {path} ({circuit.num_qubits} qubits)")


if __name__ == "__main__":
    main()
