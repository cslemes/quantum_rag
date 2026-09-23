"""Builds the reference (oracle) circuits for T4's 12 perturbed variants
(T048, T049) — one per T4 canonical task (FR-017), task_id = `<base>_
perturbed`, `base_task_id` set to the canonical's task_id. `coupling_map`
stays `"linear_5"` in every perturbed task JSON — that field, not
`oracle_kind`, is what makes a task T4 (D3h), so a perturbed T4 task that
dropped it would silently stop being a T4 task at all.

    uv run python -m bench.oracles.build_t4_perturbed

Same discipline as T1-T3 — every candidate family checked computationally,
per instance, BEFORE assignment:

  1. **Qubit-ordering vacuousness, now checked against the FULL 5-qubit
     reversal i -> 4-i** (not a smaller register — T4 is fixed at 5 qubits
     throughout). `linear_5`'s own topology (a path graph 0-1-2-3-4) is
     itself symmetric under this exact reversal (a line reversed is the same
     line), so `coupling_map` never needs to change for this family — but
     several TASKS are still vacuous under it, for the same structural
     reason as T2/T3 (D3j/D3k): whenever a term's own qubit SET is symmetric
     under i -> 4-i, the relabeling is a no-op. Checked via `Operator`/
     `Statevector .equiv(...reverse_qargs())` against every canonical
     `.qpy`, not assumed:
       - GHZ family: `ghz_linear5_full` ({0,1,2,3,4}, the whole register —
         symmetric under any permutation), `ghz_linear5_scattered_even`
         ({0,2,4} -> reversed {4,2,0}, the SAME set), and
         `ghz_linear5_endpoints` ({0,4} -> reversed {4,0}, the SAME set) are
         ALL vacuous. Only `ghz_linear5_mixed` ({0,1,4} -> reversed
         {4,3,0}, a DIFFERENT set) is non-vacuous — the only GHZ instance
         used for this family.
       - Ising family: `ising_linear5_endpoints` (single edge (0,4) ->
         reversed (4,0), the SAME edge) is vacuous; `local`, `distance2`,
         `mixed` are not.
       - Z-string family: BOTH instances vacuous — `zstring_linear5_
         scattered` ({0,2,4} -> {4,2,0}, same set) and `zstring_linear5_
         full_chain` ({0,1,2,3,4}, the whole register).
       - Field+coupling family: neither instance is vacuous (both share the
         field dict {0:0.2,1:0.3,2:-0.1,3:0.4,4:-0.3}, which is not
         palindromic under i -> 4-i: field(0)=0.2 != field(4)=-0.3).
  2. **Relative-phase and gate-set-restriction are valid for ALL twelve
     T4 instances, unconditionally** — same reasoning and same verification
     method as T3 (build_t3_perturbed.py's docstring): every T4 primary is
     H/CX/RZ only, no SWAP, so neither the global-phase blindness that
     affects a single-basis-state `statevector` target (T4's GHZ family;
     checked per relevant instance, not assumed, since GHZ IS a single-
     basis... no, GHZ is TWO-term, not single-basis, so RZ is visible there
     too — verified) nor D3k's SWAP+final_layout trap (T4 has no SWAP
     anywhere in its primary constructions either) can arise.
  3. **`check_resources` is unaffected by any of this.** It compares
     `depth()`/`cx_count()` of generated vs. reference after IDENTICAL
     `transpile(coupling_map="linear_5", optimization_level=2, seed=42)` —
     a purely structural comparison, not an equivalence check, so it was
     never at risk from D3k's `Operator()`-vs-`TranspileLayout` trap (that
     trap only affects equivalence checks). No `basis_gates` restriction is
     ever passed to `check_resources`'s own `transpile()` call, so the
     gate-set-restriction family's prompt-level constraint has no
     interaction with the resource check either way.

Family assignment (12 tasks): relative-phase (2: ising_linear5_distance2,
zstring_linear5_scattered), gate-set-restriction (3: ghz_linear5_endpoints,
ising_linear5_endpoints, field_coupling_linear5_local), qubit-ordering
(3: ghz_linear5_mixed, ising_linear5_local, field_coupling_linear5_
scattered), symbolic-parameterization (2: ghz_linear5_scattered_even —
subset stated as "every even-indexed qubit" instead of an enumerated list;
zstring_linear5_full_chain — coefficient/gamma stated as an exact fraction),
composition (2: ghz_linear5_full, ising_linear5_mixed). Spread across all
four T4 families (GHZ/Ising/Z-string/field-coupling), not concentrated.
"""

from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import QFTGate

from bench.oracles.build_t4_hardware import (
    N_QUBITS,
    field_and_coupling,
    ghz_over_subset,
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
    out.append(QFTGate(N_QUBITS), range(N_QUBITS))
    return out


# task_id -> circuit. base_task_id is recovered by stripping "_perturbed".
TASKS: dict[str, QuantumCircuit] = {
    # -- relative phase (verified non-vacuous — see docstring) --
    "ising_linear5_distance2_perturbed": _rz_perturb(
        weighted_ising({(0, 2): 0.5, (1, 3): -0.4, (2, 4): 0.3}, 0.45), 0, np.pi / 4
    ),
    "zstring_linear5_scattered_perturbed": _rz_perturb(
        zstring_hamiltonian([([0, 2, 4], 0.6)], 0.5), 0, np.pi / 4
    ),
    # -- gate-set restriction (target unchanged from canonical) --
    "ghz_linear5_endpoints_perturbed": ghz_over_subset([0, 4]),
    "ising_linear5_endpoints_perturbed": weighted_ising({(0, 4): 0.6}, 0.5),
    "field_coupling_linear5_local_perturbed": field_and_coupling(
        {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3},
        {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5},
        0.4,
    ),
    # -- qubit ordering / endianness (verified non-vacuous — see docstring) --
    "ghz_linear5_mixed_perturbed": ghz_over_subset([4, 3, 0]),
    "ising_linear5_local_perturbed": weighted_ising(
        {(0, 1): 0.4, (1, 2): -0.3, (2, 3): 0.5, (3, 4): -0.2}, 0.5
    ).reverse_bits(),
    "field_coupling_linear5_scattered_perturbed": field_and_coupling(
        {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}, {(0, 4): 0.4, (1, 3): -0.3}, 0.4
    ).reverse_bits(),
    # -- symbolic parameterization (target unchanged from canonical) --
    "ghz_linear5_scattered_even_perturbed": ghz_over_subset([0, 2, 4]),
    "zstring_linear5_full_chain_perturbed": zstring_hamiltonian([([0, 1, 2, 3, 4], 1 / 2)], 1 / 2),
    # -- composition (canonical target, then QFT on the same register) --
    "ghz_linear5_full_perturbed": _compose_qft(ghz_over_subset([0, 1, 2, 3, 4])),
    "ising_linear5_mixed_perturbed": _compose_qft(
        weighted_ising({(0, 1): 0.3, (2, 3): -0.4, (0, 4): 0.5}, 0.45)
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
