"""Builds the reference (oracle) circuits for T3's 12 perturbed variants
(T048, T049) — one per T3 canonical task (FR-017), task_id = `<base>_
perturbed`, `base_task_id` set to the canonical's task_id.

    uv run python -m bench.oracles.build_t3_perturbed

Same discipline as T1/T2 (build_t1_perturbed.py, build_t2_perturbed.py):
every candidate family was checked computationally, per instance, BEFORE
assignment — not assumed from the family name. Two checks done here, with
their outcomes, so a future reader does not have to re-derive them:

  1. **Qubit-ordering can be vacuous exactly when a Hamiltonian's terms are
     symmetric under the full-register reversal i -> n-1-i.** Checked via
     `Operator(qc).equiv(Operator(qc).reverse_qargs())` against every
     canonical `.qpy` before assignment. Two of T3's twelve are vacuous:
     `ising_zzz_3q` and `ising_zzzz_4q` — both are a SINGLE Z-string term
     spanning EVERY qubit in the register (Z0*Z1*Z2 and Z0*Z1*Z2*Z3
     respectively), and a single all-qubit product term is invariant under
     ANY permutation of its own qubits, reversal included — the same
     structural reason T2's cycle-graph QAOA instances were vacuous (D3j):
     whenever a term's own qubit set is symmetric under the relabeling,
     the relabeling is a no-op on the Hamiltonian. Both were moved to other
     families instead of forced into a vacuous qubit-ordering "perturbation".
  2. **Relative-phase and gate-set-restriction are valid for ALL twelve
     T3 instances, unconditionally** — verified, not assumed. T3's
     `oracle_kind="unitary"` check (`Operator.equiv()`) is NOT global-phase
     blind to a single-qubit RZ the way T1/T2's `Statevector.equiv()` was on
     a single-basis-state target (D3j #2): RZ(phi) tensored with identity on
     the rest of an n>=2-qubit register is never a multiple of the identity
     for phi != 0 (mod 2*pi), so it always changes the full unitary — checked
     for one RZ(pi/4) on qubit 0 against every instance, all non-vacuous.
     Gate-set restriction to {rz, sx, x, cx} is also unconditionally safe
     here: every T3 primary circuit is built from H, CX, and RZ only — NO
     SWAP gate appears anywhere in T3's construction (`_zstring_term`'s CNOT
     ladder never swaps), so the `TranspileLayout.final_layout` elision found
     in T2 (D3k — confirmed NOT a Qiskit bug, but requires a SWAP gate to
     trigger at all) cannot arise here regardless of `optimization_level`.
     Checked (not assumed) via `transpile()` at opt_level 1/2/3 for all
     twelve instances, all agree exactly with `Operator()` (no D3k trap).

Family assignment (12 tasks): relative-phase (2: ising_weighted_maxcut_3q,
ising_field_coupling_4q), gate-set-restriction (3: ising_weighted_maxcut_4q,
ising_mixed_body_4q, qubo_ising_3var), qubit-ordering (3: ising_weighted_
maxcut_5q, ising_field_coupling_3q, qubo_ising_4var), symbolic-
parameterization (2: ising_zzz_3q, qubo_ising_5var — gamma restated as an
exact fraction instead of a decimal), composition (2: ising_zzzz_4q,
ising_field_coupling_5q). Spread across all four T3 formulation-families
(A/B/C/D), not concentrated in one.

For "same target as canonical" families (gate-set-restriction, symbolic-
parameterization), the perturbed oracle calls the EXACT SAME canonical
construction function from `build_t3_formulation.py` with the SAME
arguments — same reasoning as T2's perturbed build (the independence
discipline belongs to `validate_oracles.py`'s alternative-construction
check, not to matching-target reuse here).
"""

from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import QFTGate

from bench.oracles.build_t3_formulation import (
    field_and_coupling,
    ising_from_qubo,
    weighted_ising,
    zstring_hamiltonian,
)

OUT_DIR = Path(__file__).parent


def _rz_perturb(qc: QuantumCircuit, qubit: int, phi: float) -> QuantumCircuit:
    out = qc.copy()
    out.rz(phi, qubit)
    return out


def _compose_qft(qc: QuantumCircuit) -> QuantumCircuit:
    out = qc.copy()
    out.append(QFTGate(qc.num_qubits), range(qc.num_qubits))
    return out


# task_id -> circuit. base_task_id is recovered by stripping "_perturbed".
TASKS: dict[str, QuantumCircuit] = {
    # -- relative phase (verified non-vacuous for all T3 — see docstring) --
    "ising_weighted_maxcut_3q_perturbed": _rz_perturb(
        weighted_ising(3, {(0, 1): 0.6, (1, 2): -0.4, (0, 2): 0.9}, 0.5), 0, np.pi / 4
    ),
    "ising_field_coupling_4q_perturbed": _rz_perturb(
        field_and_coupling(4, {0: 0.2, 1: -0.4, 2: 0.3, 3: 0.1}, {(0, 1): 0.5, (2, 3): 0.3}, 0.45),
        0,
        np.pi / 4,
    ),
    # -- gate-set restriction (target unchanged from canonical) --
    "ising_weighted_maxcut_4q_perturbed": weighted_ising(
        4, {(0, 1): 0.3, (1, 2): 0.7, (2, 3): -0.5, (0, 3): 0.4}, 0.45
    ),
    "ising_mixed_body_4q_perturbed": zstring_hamiltonian(4, [([0, 1], 0.4), ([1, 2, 3], 0.6)], 0.5),
    "qubo_ising_3var_perturbed": field_and_coupling(
        3, *ising_from_qubo([[2, -1, 0.5], [0, -3, 1.5], [0, 0, 1]], 3), 0.5
    ),
    # -- qubit ordering / endianness (verified non-vacuous — see docstring) --
    "ising_weighted_maxcut_5q_perturbed": weighted_ising(
        5, {(0, 1): 0.5, (0, 2): -0.3, (0, 3): 0.8, (0, 4): 0.2}, 0.4
    ).reverse_bits(),
    "ising_field_coupling_3q_perturbed": field_and_coupling(
        3, {0: 0.3, 1: 0.5, 2: -0.2}, {(0, 1): 0.4}, 0.5
    ).reverse_bits(),
    "qubo_ising_4var_perturbed": field_and_coupling(
        4,
        *ising_from_qubo(
            [[1.5, -0.8, 0.6, 0.0], [0, -2.0, 0.4, 0.9], [0, 0, 1.0, -0.7], [0, 0, 0, 0.5]], 4
        ),
        0.45,
    ).reverse_bits(),
    # -- symbolic parameterization (target unchanged; gamma as a fraction) --
    "ising_zzz_3q_perturbed": zstring_hamiltonian(3, [([0, 1, 2], 0.7)], 3 / 5),
    "qubo_ising_5var_perturbed": field_and_coupling(
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
        2 / 5,
    ),
    # -- composition (canonical target, then QFT on the same register) --
    "ising_zzzz_4q_perturbed": _compose_qft(zstring_hamiltonian(4, [([0, 1, 2, 3], 0.5)], 0.5)),
    "ising_field_coupling_5q_perturbed": _compose_qft(
        field_and_coupling(
            5,
            {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3},
            {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5},
            0.4,
        )
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
