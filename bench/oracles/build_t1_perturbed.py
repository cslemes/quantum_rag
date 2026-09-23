"""Builds the reference (oracle) circuits for T1's 18 perturbed variants
(T048, T049) — one per T1 canonical task (FR-017), task_id = `<base>_
perturbed`, `base_task_id` set to the canonical's task_id.

    uv run python -m bench.oracles.build_t1_perturbed

Five families (D12), distributed across T1's 18 tasks rather than
concentrated (4/4/4/3/3 split) so `delta_perturbacao` (T063, FR-023) can be
segmented by family without confounding it with tier difficulty:

  - **Relative phase** (4): bell_phi_plus_2q, ghz_3q, ghz_8q, w_state_3q —
    same magnitude structure as canonical, a stated nonzero relative phase
    between the two (or, for W-state, one) branches. Primary is
    `StatePreparation` on the phase-inserted closed-form vector (same
    zero-derivation-risk reasoning as D3c); the alternative in
    `bench/validate_oracles.py` is the canonical's OWN hand-gate
    construction plus a trailing `RZ` on one qubit — verified (not assumed)
    to reach the same target up to global phase before being trusted here.
  - **Gate-set restriction** (4): bell_phi_minus_2q, ghz_5q,
    reversible_half_adder_4q, w_state_5q — SAME target as canonical (the
    oracle is a byte-identical rebuild of the canonical circuit); the
    restriction lives entirely in the TASK PROMPT (`{rz, sx, x, cx}`, a
    standard IBM hardware-native set), not in the oracle. Chosen over a
    Clifford+T basis after a real, verified dead end: `{h, cx, s, t, sdg,
    tdg}` cannot express QFT-3's controlled-phase gates via Qiskit's own
    equivalence library (`transpile()` raises `TranspilerError` at every
    optimization level) — {rz, sx, x, cx} is universal and was verified
    solvable for all four tasks via `transpile()` + `Operator`/`Statevector.
    equiv()` before being used here.
  - **Qubit ordering / explicit endianness** (4): dj_constant_4q,
    dj_balanced_6q, qft_8q, reversible_full_adder_5q — `.reverse_bits()` of
    the canonical reference (dj_*, reversible_full_adder) or QFT's own
    `do_swaps=False` convention (qft_8q — a real, standard QFT variant, not
    an invented one). Each was verified (not assumed) to produce a target
    GENUINELY DIFFERENT from the canonical before being used — GHZ and
    W-state are symmetric under `reverse_bits()` (a permutation-invariant
    uniform superposition), so they would have been no-op "perturbations"
    and are deliberately NOT in this family.
  - **Composition** (3): bell_psi_plus_2q, w_state_8q,
    reversible_boolean4_8q — canonical target composed with QFT on the same
    register (QFT chosen as the second stage for all three: already
    verified at every qubit count T1 uses, and composing with it is a
    genuinely different circuit from either building block alone). Verified
    via direct `Statevector.evolve`/`Operator` product against each
    hand-built composed circuit before use.
  - **Symbolic parameterization** (3): qft_3q, qft_5q, dj_balanced_4q — SAME
    oracle as canonical; the perturbation is entirely in the PROMPT, which
    states a formula (QFT's phase angles as `2*pi/2^k`; DJ's secret as a
    small computed integer) instead of handing over already-evaluated
    numbers, without changing the target.

FR-018 undeclared-constraint discipline (D3g) applies here as much as to the
canonical set — arguably more, per the user's framing, since perturbing a
task is exactly the moment an implicit assumption becomes a silent
constraint: every gate-set-restricted prompt states the exact allowed gate
list; every reversed-ordering prompt states the convention explicitly, not
just "note the ordering matters."
"""

from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import QFTGate, StatePreparation

OUT_DIR = Path(__file__).parent


# -- Relative phase -----------------------------------------------------


def _phase_ghz_like(n: int, one_indices: list[int], phi: float) -> QuantumCircuit:
    """Closed-form target: (|0...0> + e^{i*phi}*|one bits set at
    one_indices>) / sqrt(2)."""
    dim = 2**n
    target = np.zeros(dim, dtype=complex)
    target[0] = 1 / np.sqrt(2)
    target[sum(1 << i for i in one_indices)] = np.exp(1j * phi) / np.sqrt(2)
    qc = QuantumCircuit(n)
    qc.append(StatePreparation(target), range(n))
    return qc


def _phase_w_state(n: int, phase_qubit: int, phi: float) -> QuantumCircuit:
    """W-state target with an extra relative phase phi on the single term
    where `phase_qubit` is the |1>."""
    dim = 2**n
    target = np.zeros(dim, dtype=complex)
    for i in range(n):
        amp = np.exp(1j * phi) if i == phase_qubit else 1.0
        target[1 << i] = amp / np.sqrt(n)
    qc = QuantumCircuit(n)
    qc.append(StatePreparation(target), range(n))
    return qc


# -- Gate-set restriction (SAME target as canonical — rebuilt identically) --


def _bell_phi_minus() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.z(0)
    return qc


def _ghz_chain(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(0)
    for i in range(n - 1):
        qc.cx(i, i + 1)
    return qc


def _half_adder() -> QuantumCircuit:
    qc = QuantumCircuit(4)
    a, b, s, c = range(4)
    qc.cx(a, s)
    qc.cx(b, s)
    qc.ccx(a, b, c)
    return qc


def _w_state_chain(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.x(0)
    for k in range(n - 1):
        theta = 2 * np.arccos(np.sqrt(1 / (n - k)))
        qc.cry(theta, k, k + 1)
        qc.cx(k + 1, k)
    return qc


# -- Qubit ordering / endianness ----------------------------------------


def _deutsch_jozsa(n_input: int, secret: int | None) -> QuantumCircuit:
    """Same construction as the T1 canonical `deutsch_jozsa()`
    (build_t1_primitives.py): control varies per set-bit position `i`, not a
    fixed qubit. An earlier draft used a fixed control `j` (lowest set bit)
    repeated once per set bit — since CX is self-inverse, that collapses any
    multi-bit secret to just `x_j` (odd repetition count) or the identity
    (even count), silently building the wrong balanced function. Caught by
    comparing against the canonical before use."""
    qc = QuantumCircuit(n_input + 1)
    qc.x(n_input)
    qc.h(range(n_input + 1))
    if secret is not None:
        for i in range(n_input):
            if (secret >> i) & 1:
                qc.cx(i, n_input)
    qc.h(range(n_input))
    return qc


def _qft_no_swap(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    for j in reversed(range(n)):
        qc.h(j)
        for k in range(j):
            qc.cp(np.pi / (2 ** (j - k)), k, j)
    return qc  # deliberately no final swap layer (do_swaps=False convention)


def _full_adder() -> QuantumCircuit:
    qc = QuantumCircuit(5)
    a, b, cin, s, cout = range(5)
    qc.cx(a, s)
    qc.cx(b, s)
    qc.cx(cin, s)
    qc.ccx(a, b, cout)
    qc.ccx(b, cin, cout)
    qc.ccx(a, cin, cout)
    return qc


# -- Composition ----------------------------------------------------------


def _bell_psi_plus() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.x(1)
    return qc


def _boolean4() -> QuantumCircuit:
    qc = QuantumCircuit(8)
    a, b, c, d, o_par, o_and4, o_ab, o_cd = range(8)
    qc.cx(a, o_par)
    qc.cx(b, o_par)
    qc.cx(c, o_par)
    qc.cx(d, o_par)
    qc.mcx([a, b, c, d], o_and4)
    qc.ccx(a, b, o_ab)
    qc.ccx(c, d, o_cd)
    return qc


def _compose_with_qft(base: QuantumCircuit) -> QuantumCircuit:
    qc = base.copy()
    qc.append(QFTGate(base.num_qubits), range(base.num_qubits))
    return qc


def _qft_with_swap(n: int) -> QuantumCircuit:
    """The standard QFT convention (with the final swap layer) — the SAME
    target as the T1 canonical qft_Nq oracles. Used by the symbolic-
    parameterization perturbations (qft_3q/qft_5q), which reuse the
    canonical target unchanged; `_qft_no_swap` above is a DIFFERENT
    convention used only by qft_8q's ordering perturbation.
    """
    qc = _qft_no_swap(n)
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


# task_id -> circuit. base_task_id is recovered by stripping "_perturbed".
TASKS: dict[str, QuantumCircuit] = {
    # -- relative phase --
    "bell_phi_plus_2q_perturbed": _phase_ghz_like(2, [0, 1], np.pi / 3),
    "ghz_3q_perturbed": _phase_ghz_like(3, [0, 1, 2], 2 * np.pi / 5),
    "ghz_8q_perturbed": _phase_ghz_like(8, list(range(8)), np.pi / 6),
    "w_state_3q_perturbed": _phase_w_state(3, 2, np.pi / 2),
    # -- gate-set restriction (target unchanged from canonical) --
    "bell_phi_minus_2q_perturbed": _bell_phi_minus(),
    "ghz_5q_perturbed": _ghz_chain(5),
    "reversible_half_adder_4q_perturbed": _half_adder(),
    "w_state_5q_perturbed": _w_state_chain(5),
    # -- qubit ordering / endianness --
    "dj_constant_4q_perturbed": _deutsch_jozsa(3, None).reverse_bits(),
    "dj_balanced_6q_perturbed": _deutsch_jozsa(5, 0b10110).reverse_bits(),
    "qft_8q_perturbed": _qft_no_swap(8),
    "reversible_full_adder_5q_perturbed": _full_adder().reverse_bits(),
    # -- composition (canonical target, then QFT on the same register) --
    "bell_psi_plus_2q_perturbed": _compose_with_qft(_bell_psi_plus()),
    "w_state_8q_perturbed": _compose_with_qft(_w_state_chain(8)),
    "reversible_boolean4_8q_perturbed": _compose_with_qft(_boolean4()),
    # -- symbolic parameterization (target unchanged from canonical) --
    "qft_3q_perturbed": _qft_with_swap(3),
    "qft_5q_perturbed": _qft_with_swap(5),
    "dj_balanced_4q_perturbed": _deutsch_jozsa(3, 0b101),
}


def main() -> None:
    for task_id, circuit in TASKS.items():
        path = OUT_DIR / f"{task_id}.qpy"
        with open(path, "wb") as f:
            qpy.dump(circuit, f)
        print(f"wrote {path} ({circuit.num_qubits} qubits)")


if __name__ == "__main__":
    main()
