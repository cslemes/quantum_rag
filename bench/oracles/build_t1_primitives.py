"""Builds the reference (oracle) circuits for the 18 T1 canonical tasks
(T044, T049) and serializes each to `bench/oracles/<task_id>.qpy`.

    uv run python -m bench.oracles.build_t1_primitives

Principle V / FR-018: an oracle must be verified by construction INDEPENDENT
of the task's own reasoning, not merely re-derived from the prompt. This
module is the PRIMARY construction only — `bench/validate_oracles.py` holds
a second, deliberately different construction per family (never imported
from here) and checks the two agree. Splitting them into separate modules
with zero shared helper code is the point: sharing a helper function between
primary and alternative would let one bug hide in both.

Per family, the primary construction here is whichever of two equally-valid
methods carries the LOWER risk of a hand-derivation error:
  - Bell / GHZ / W-state: `StatePreparation` from an explicit, closed-form
    target amplitude vector written directly from the state's mathematical
    definition (e.g. GHZ's vector has exactly two nonzero entries) — there
    is no gate-sequence reasoning to get wrong.
  - QFT: the standard textbook gate sequence (H + controlled-phase + final
    swaps) — well-established and low-risk to transcribe correctly.
  - Deutsch-Jozsa: the standard ancilla-based bit-flip-oracle circuit (H's,
    CNOTs from each "active" input qubit into the ancilla, H's on the input
    register) — the construction the task's prompt itself describes step by
    step, matching how the algorithm is universally taught.
  - Reversible boolean arithmetic (half adder, full adder, a 4-output
    boolean batch): plain CNOT/Toffoli/MCX gates computing each output
    directly from the original inputs. See D3d, research.md, for why every
    one of these is deliberately FLAT (no output/ancilla is ever used as a
    control for computing another output) — a chained (non-flat) design was
    tried first and rejected after the independent-construction check
    itself caught the problem.

Ancilla convention (Deutsch-Jozsa only, stated explicitly since it is NOT
implied by D3c's endianness trap): the ancilla is the highest-indexed qubit
(qubit n for an n-input-qubit oracle), matching each task's prompt text
verbatim so the generated circuit and the oracle agree on qubit assignment
before any correctness question is even asked.
"""

from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import StatePreparation

OUT_DIR = Path(__file__).parent


def bell_state(kind: str) -> QuantumCircuit:
    """kind in {"phi_plus", "phi_minus", "psi_plus"} — three of the four
    Bell basis states, distinct canonical targets at n_qubits=2."""
    target = np.zeros(4, dtype=complex)
    if kind == "phi_plus":
        target[0b00] = target[0b11] = 1 / np.sqrt(2)
    elif kind == "phi_minus":
        target[0b00] = 1 / np.sqrt(2)
        target[0b11] = -1 / np.sqrt(2)
    elif kind == "psi_plus":
        target[0b01] = target[0b10] = 1 / np.sqrt(2)
    else:
        raise ValueError(f"unknown Bell kind {kind!r}")
    qc = QuantumCircuit(2)
    qc.append(StatePreparation(target), [0, 1])
    return qc


def ghz_state(n: int) -> QuantumCircuit:
    """(|0...0> + |1...1>) / sqrt(2) — exactly two nonzero amplitudes."""
    target = np.zeros(2**n, dtype=complex)
    target[0] = target[2**n - 1] = 1 / np.sqrt(2)
    qc = QuantumCircuit(n)
    qc.append(StatePreparation(target), range(n))
    return qc


def w_state(n: int) -> QuantumCircuit:
    """Equal superposition over every weight-1 computational basis state
    (exactly one qubit in |1>). Amplitude 1/sqrt(n) at each of the n
    single-bit-set indices — direct from the definition, no rotation-angle
    derivation needed."""
    target = np.zeros(2**n, dtype=complex)
    for i in range(n):
        target[1 << i] = 1 / np.sqrt(n)
    qc = QuantumCircuit(n)
    qc.append(StatePreparation(target), range(n))
    return qc


def qft(n: int) -> QuantumCircuit:
    """Standard textbook QFT: H + controlled-phase cascade processing qubits
    from highest index down to lowest, then a final qubit-order reversal via
    SWAPs (matching the conventional definition and Qiskit's own
    `do_swaps=True` default — the task's prompt states this convention
    explicitly so the generated circuit and this oracle agree on it before
    any correctness question is asked).

    CAUTION: an earlier version of this function processed qubits low-to-high
    with the control on the higher-indexed qubit — it type-checked and ran,
    but produced the WRONG unitary (only caught by cross-checking against
    `qiskit.circuit.library.QFTGate` in validate_oracles.py, exactly the
    failure mode FR-018's independent-construction requirement exists to
    catch). The direction below (high-to-low, control on the LOWER qubit) is
    the one verified to agree with `QFTGate` for n in {2,3,5,8}.
    """
    qc = QuantumCircuit(n)
    for j in reversed(range(n)):
        qc.h(j)
        for k in range(j):
            qc.cp(np.pi / (2 ** (j - k)), k, j)
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


def deutsch_jozsa(n_input: int, secret: int | None) -> QuantumCircuit:
    """Standard ancilla-based bit-flip-oracle DJ circuit. `secret=None` is
    the constant-zero oracle (no CNOTs at all — f(x)=0 for every x);
    otherwise `secret` is the bitmask of input qubits the (linear, hence
    balanced) oracle XORs into the ancilla. Ancilla is qubit `n_input`
    (highest index) — see module docstring.
    """
    qc = QuantumCircuit(n_input + 1)
    qc.x(n_input)
    qc.h(range(n_input + 1))
    if secret is not None:
        for i in range(n_input):
            if (secret >> i) & 1:
                qc.cx(i, n_input)
    qc.h(range(n_input))
    return qc


def reversible_half_adder() -> QuantumCircuit:
    """a=0, b=1, sum=2, carry=3. FLAT: every gate's controls are original
    input qubits (a, b) only — sum/carry are targets, never controls for
    anything else. This is what makes `oracle_kind="unitary"` sound for this
    family (D3d, research.md): a flat circuit's action on every one of the
    2^4 computational-basis inputs — not just the 4 "physical" ones where
    sum/carry start at |0> — is uniquely determined by the boolean
    definition alone, regardless of which valid gate sequence computes it.
    """
    qc = QuantumCircuit(4)
    a, b, s, c = range(4)
    qc.cx(a, s)
    qc.cx(b, s)
    qc.ccx(a, b, c)
    return qc


def reversible_full_adder() -> QuantumCircuit:
    """a=0, b=1, cin=2, sum=3, cout=4. Flat, same reasoning as the half
    adder — cin is an original input (a control), sum/cout are targets only.
    """
    qc = QuantumCircuit(5)
    a, b, cin, s, cout = range(5)
    qc.cx(a, s)
    qc.cx(b, s)
    qc.cx(cin, s)
    qc.ccx(a, b, cout)
    qc.ccx(b, cin, cout)
    qc.ccx(a, cin, cout)
    return qc


def reversible_boolean4() -> QuantumCircuit:
    """a,b,c,d = 0,1,2,3; four independent outputs (parity, 4-input AND,
    a AND b, c AND d) at qubits 4-7. Flat: all four outputs are computed
    directly from the four original inputs, never from each other.

    NOTE (D3d): a 2-bit ripple-carry adder — chaining one stage's carry
    ancilla into a second stage as a CONTROL — was tried first and
    REJECTED here after `check_alternative_construction` caught it
    disagreeing with its own closed-form cross-check on the "non-physical"
    part of the domain (ancillas not starting at |0>). See research.md D3d
    for the full finding; this flat 4-output design was the fix.
    """
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


# task_id -> circuit, single source of truth for both the build step below
# and (by task_id lookup, not by importing these functions) validate_oracles.py.
TASKS: dict[str, QuantumCircuit] = {
    "bell_phi_plus_2q": bell_state("phi_plus"),
    "bell_phi_minus_2q": bell_state("phi_minus"),
    "bell_psi_plus_2q": bell_state("psi_plus"),
    "ghz_3q": ghz_state(3),
    "ghz_5q": ghz_state(5),
    "ghz_8q": ghz_state(8),
    "w_state_3q": w_state(3),
    "w_state_5q": w_state(5),
    "w_state_8q": w_state(8),
    "qft_3q": qft(3),
    "qft_5q": qft(5),
    "qft_8q": qft(8),
    "dj_constant_4q": deutsch_jozsa(3, None),
    "dj_balanced_4q": deutsch_jozsa(3, 0b101),
    "dj_balanced_6q": deutsch_jozsa(5, 0b10110),
    "reversible_half_adder_4q": reversible_half_adder(),
    "reversible_full_adder_5q": reversible_full_adder(),
    "reversible_boolean4_8q": reversible_boolean4(),
}


def main() -> None:
    for task_id, circuit in TASKS.items():
        path = OUT_DIR / f"{task_id}.qpy"
        with open(path, "wb") as f:
            qpy.dump(circuit, f)
        print(f"wrote {path} ({circuit.num_qubits} qubits)")


if __name__ == "__main__":
    main()
