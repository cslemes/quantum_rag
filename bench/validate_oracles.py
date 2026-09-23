"""Blocking oracle-validation gate — T050. FR-018: every evaluation reference
must be verified by construction INDEPENDENT of how the task was written,
plus property-checking, in an automated blocking process.

    uv run python -m bench.validate_oracles
    make validate-oracles

Four checks per oracle, all of which must pass:

  1. **unitariedade / normalização** — the oracle circuit is itself a valid
     physical object: `U @ U^dagger ≈ I` for `oracle_kind="unitary"`, or the
     statevector norm ≈ 1 for `oracle_kind="statevector"`.
  2. **construção alternativa** — a SECOND construction of the same target,
     written independently of `bench/oracles/build_t1_primitives.py` (no
     shared helper code, no import from that module — sharing a helper
     would let one bug hide in both constructions), checked equivalent to
     the primary oracle via `Operator.equiv`/`Statevector.equiv`.
  3. **cross-check com biblioteca** — where Qiskit ships a tested library
     implementation of the algorithm (only QFT, among the T1 families —
     confirmed empirically: `qiskit.circuit.library` has no GHZ, W-state, or
     Deutsch-Jozsa primitive), cross-check against it too. Reported N/A,
     not silently skipped, when no such primitive exists.
  4. **sanity em 3 seeds** — a real `AerSimulator` run (seeds 1, 2, 3, same
     convention as `validators/semantic.py`'s `check_distribution`), measured
     counts compared via Hellinger fidelity against a target derived from the
     INDEPENDENT alternative construction (never from the primary oracle
     itself — see `check_sanity_seeds`'s docstring for why an earlier version
     of this check, which compared against a target derived from the primary,
     was hiding a real blind spot for `oracle_kind="unitary"`). This exercises
     the real simulation/transpilation path, which a pure linear-algebra
     comparison between two hand-typed circuits never touches — but it is NOT
     a substitute for checks 1-2's exact correctness guarantee, and is not
     calibrated as if it could catch every construction bug they catch.

`SANITY_FIDELITY_MIN` is calibrated against measured SHOT-NOISE, not against
construction correctness (checks 1-2 give that exactly, with zero sampling
noise — no tolerance value in this check changes what they can or cannot
catch). Monte Carlo (500 trials, N=8192 shots, this repo's actual shot count)
against the worst case in this dataset — a uniform distribution over 256
outcomes (QFT-8q) — gives a shot-noise-only fidelity floor of mean=0.9922,
worst-observed=0.9892 in 500 trials. `SANITY_FIDELITY_MIN=0.98` sits
comfortably below that floor (~0.009-0.012 margin), so it will not fail a
genuinely correct oracle to shot noise alone. It is deliberately NOT tuned
tighter to try to catch subtler bugs — see `check_sanity_seeds`'s docstring
for why that job belongs to checks 1-2, not this one.

This module currently only registers T1 families — it iterates every
`bench/tasks/**/*.json` it finds, so T2-T4 register by adding a matching
`task_id` branch to `_build_alternatives` below when those tiers are built
(T045-T047); an unregistered family fails loudly (`KeyError`) rather than
silently skipping validation.
"""

import json
import sys
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy, transpile
from qiskit.circuit.library import Diagonal, QFTGate, RZGate, StatePreparation, UnitaryGate
from qiskit.quantum_info import Operator, SparsePauliOp, Statevector, hellinger_fidelity
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh

from bench.schema import TaskSpec
from qcagent.validators.simulator import make_simulator

TASKS_DIR = Path("bench/tasks")
SANITY_SHOTS = 8192
SANITY_SEEDS = (1, 2, 3)
SANITY_FIDELITY_MIN = 0.98

# D3e (research.md): the phase-blindness finding from T1's QFT is not QFT-
# specific — ANY oracle whose alternative-derived target distribution is
# spread (no single outcome clearly dominates) has the same structural blind
# spot for a direct measurement-vs-alternative-derived-target comparison.
# Below this threshold, check_sanity_seeds switches to the round-trip design
# regardless of oracle_kind. Measured while building T2: Simon's full joint
# state is exactly uniform over 2^n outcomes (max ~1/2^n); Grover before
# near-optimal amplification is comparably spread; QAOA at realistic p=1
# angles measured max probability 0.11-0.37 across the three T2 instances
# built. 0.9 is a single computed threshold applied uniformly, not carved
# into per-family exceptions (see check_sanity_seeds's docstring) — this
# also routes some LOW-RISK cases (e.g. Bernstein-Vazirani's ancilla-driven
# 0.5/0.5 split across only two outcomes, not a genuinely spread target) to
# the round-trip design too. That is accepted as conservative, not wrong:
# the round-trip check is never less informative than a direct comparison,
# so applying it somewhere it wasn't strictly necessary costs nothing but
# compute.
PEAKEDNESS_THRESHOLD = 0.9


# -- Independent ("alternative") constructions — deliberately NOT imported
# from bench/oracles/build_t1_primitives.py. See module docstring.


def _alt_bell(kind: str) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    if kind == "phi_minus":
        qc.z(0)
    elif kind == "psi_plus":
        qc.x(1)
    return qc


def _alt_ghz(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(0)
    for q in range(n - 1):
        qc.cx(q, q + 1)
    return qc


def _alt_ghz_subset(n: int, subset: list[int]) -> Statevector:
    """T4's GHZ family (D3h): the primary is now a hand-rolled H+CX chain
    (flipped from T1's StatePreparation-primary/chain-alternative, since a
    resource-focused tier needs the REFERENCE's own transpiled depth to be
    representative, not inflated by generic synthesis — see build_t4_
    hardware.py's docstring). The alternative here is the closed-form
    target vector `StatePreparation` would prepare — same construction T1
    used as PRIMARY, now playing the alternative role instead. Independence
    survives the role swap: this function is never called by the primary
    (built in a different module) and vice versa.
    """
    dim = 2**n
    target = np.zeros(dim, dtype=complex)
    target[0] = 1 / np.sqrt(2)
    target[sum(1 << q for q in subset)] = 1 / np.sqrt(2)
    return Statevector(target)


def _alt_w_state(n: int) -> QuantumCircuit:
    """Recursive controlled-rotation construction — a different algorithm
    entirely from the primary's `StatePreparation`-from-target-vector.
    Verified (before being trusted here) to agree with the closed-form
    target for n in {3,5,8}."""
    qc = QuantumCircuit(n)
    qc.x(0)
    for k in range(n - 1):
        theta = 2 * np.arccos(np.sqrt(1 / (n - k)))
        qc.cry(theta, k, k + 1)
        qc.cx(k + 1, k)
    return qc


def _alt_qft(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.append(QFTGate(n), range(n))
    return qc


def _alt_deutsch_jozsa(n_input: int, secret: int | None) -> QuantumCircuit:
    """Phase-oracle formulation (`Diagonal`, a genuine library primitive) on
    the input register alone, tensored with the ancilla's closed-form |->
    state — a structurally different circuit from the primary's ancilla+CX
    bit-flip-oracle construction, using Qiskit's own Diagonal gate rather
    than hand-placed CX gates for the oracle itself.

    Ancilla goes on the HIGH-index side of the tensor because the primary
    circuit puts it at qubit `n_input` (the highest index) — verified
    empirically, not assumed, since Statevector.tensor()'s qubit-index
    convention is not obvious from the method name alone.
    """
    diag = (
        [1] * (2**n_input)
        if secret is None
        else [(-1) ** (bin(x & secret).count("1") % 2) for x in range(2**n_input)]
    )
    inp = QuantumCircuit(n_input)
    inp.h(range(n_input))
    inp.append(Diagonal(diag), range(n_input))
    inp.h(range(n_input))
    return Statevector.from_label("-").tensor(Statevector(inp))


def _closed_form_permutation(n_qubits: int, delta_fn) -> QuantumCircuit:
    """Builds a reversible boolean function's FULL permutation (all
    2**n_qubits computational-basis inputs, not just the "physical" ones)
    directly from `delta_fn` — a pure function of the input bits, with NO
    reference to any gate sequence — and wraps it as a single opaque
    `UnitaryGate`. This is the permutation-matrix analogue of Bell/GHZ's
    closed-form target vector: `delta_fn` must be FLAT (its returned deltas
    depend only on ORIGINAL input bits, never on another output bit) or the
    permutation isn't uniquely defined off the physical subspace — see D3d,
    research.md, for the ripple-carry-adder case where getting this wrong
    was caught by exactly this check disagreeing with the primary circuit.
    """
    dim = 2**n_qubits
    matrix = np.zeros((dim, dim))
    for x in range(dim):
        bits = [(x >> i) & 1 for i in range(n_qubits)]
        new_bits = list(bits)
        for q, d in delta_fn(bits).items():
            new_bits[q] ^= d
        y = sum(bit << i for i, bit in enumerate(new_bits))
        matrix[y, x] = 1
    qc = QuantumCircuit(n_qubits)
    qc.append(UnitaryGate(matrix), range(n_qubits))
    return qc


def _alt_half_adder() -> QuantumCircuit:
    def delta_fn(bits: list[int]) -> dict[int, int]:
        a, b = bits[0], bits[1]
        return {2: a ^ b, 3: a & b}

    return _closed_form_permutation(4, delta_fn)


def _alt_full_adder() -> QuantumCircuit:
    def delta_fn(bits: list[int]) -> dict[int, int]:
        a, b, cin = bits[0], bits[1], bits[2]
        return {3: a ^ b ^ cin, 4: (a & b) ^ (b & cin) ^ (a & cin)}

    return _closed_form_permutation(5, delta_fn)


def _alt_boolean4() -> QuantumCircuit:
    def delta_fn(bits: list[int]) -> dict[int, int]:
        a, b, c, d = bits[0], bits[1], bits[2], bits[3]
        return {4: a ^ b ^ c ^ d, 5: a & b & c & d, 6: a & b, 7: c & d}

    return _closed_form_permutation(8, delta_fn)


# -- T1 perturbed (T048) independent constructions — deliberately NOT
# imported from bench/oracles/build_t1_perturbed.py. Gate-set-restriction and
# symbolic-parameterization families reuse the CANONICAL alternatives above
# unchanged (same target as canonical, verified — see that module's
# docstring); only relative-phase, qubit-ordering and composition need new
# constructions, built below.


def _alt_phase_bell(phi: float) -> Statevector:
    """Relative-phase family: the canonical Bell alternative plus a single
    RZ on qubit 0. RZ(phi) on either qubit of a 2-branch superposition
    (|00>, |11>) multiplies the two branches by e^{-i*phi/2} and e^{i*phi/2}
    respectively — exactly a relative phase of `phi` between them, up to
    overall global phase. Verified against the primary before use."""
    qc = _alt_bell("phi_plus")
    qc.rz(phi, 0)
    return Statevector(qc)


def _alt_phase_ghz(n: int, phi: float) -> Statevector:
    """Same RZ-on-one-qubit trick as `_alt_phase_bell`, generalized: GHZ's
    target is also exactly two branches (|0...0>, |1...1>), so RZ on ANY
    single qubit adds the same relative phase between them."""
    qc = _alt_ghz(n)
    qc.rz(phi, 0)
    return Statevector(qc)


def _alt_phase_w_state(n: int, phase_qubit: int, phi: float) -> Statevector:
    """W-state relative-phase family: within the W state's support, exactly
    one basis state has `phase_qubit` set to |1> — so RZ(phi) on that qubit
    adds the phase to that single term only, leaving the others' RELATIVE
    phase among themselves at zero, matching the target's definition."""
    qc = _alt_w_state(n)
    qc.rz(phi, phase_qubit)
    return Statevector(qc)


def _alt_dj_reversed(n_input: int, secret: int | None) -> Statevector:
    """Qubit-ordering family: the canonical DJ alternative, bit-reversed via
    `Statevector.reverse_qargs()` — a generic, library-verified relabeling
    operation, not a hand-rebuilt construction that could share a bug with
    either the primary or the un-reversed alternative."""
    return _alt_deutsch_jozsa(n_input, secret).reverse_qargs()


def _alt_qft_no_swap(n: int) -> QuantumCircuit:
    """Qubit-ordering family (qft_8q_perturbed): the library QFTGate (which
    includes its own internal swap layer) with an EXPLICIT swap layer
    appended afterward to cancel it back out — verified to match the
    primary's do_swaps=False convention before use. Independent of the
    primary's hand-rolled Hadamard/controlled-phase loop."""
    qc = QuantumCircuit(n)
    qc.append(QFTGate(n), range(n))
    for i in range(n // 2):
        qc.swap(i, n - 1 - i)
    return qc


def _alt_full_adder_reversed() -> QuantumCircuit:
    """Qubit-ordering family: the canonical full-adder alternative (a flat
    closed-form permutation), bit-reversed via `.reverse_bits()`."""
    return _alt_full_adder().reverse_bits()


def _alt_compose_with_qft(base: QuantumCircuit) -> QuantumCircuit:
    """Composition family: append the library QFTGate to an independently-
    rebuilt base circuit. The QFT half is the same library primitive already
    trusted as the canonical qft_Nq tasks' own alternative (is_library=True
    there); independence for the composed task comes from the base circuit
    being rebuilt from scratch, not shared with build_t1_perturbed.py."""
    qc = base.copy()
    qc.append(QFTGate(base.num_qubits), range(base.num_qubits))
    return qc


# -- T2 (T045) independent constructions — deliberately NOT imported from
# bench/oracles/build_t2_algorithms.py. All return a Statevector directly
# rather than a QuantumCircuit: none of them needs a hand-built alt_circuit
# for check_sanity_seeds's round-trip (see that function's docstring for why
# `StatePreparation(alt.data)`, derived generically from any independent
# Statevector, is sufficient and not tautological the way primary.inverse()
# would be).


def _alt_bernstein_vazirani(n_input: int, secret: int) -> Statevector:
    """Identical reasoning to T1's Deutsch-Jozsa alternative (same phase-
    oracle-via-Diagonal technique) — BV's linear oracle has the same
    mathematical shape as DJ's balanced oracle, so the same independent
    construction method applies without alteration."""
    return _alt_deutsch_jozsa(n_input, secret)


def _alt_simon(n: int, secret: int) -> Statevector:
    """Closed-form double sum, independent of any gate sequence:
    final = (1/2^n) * sum_x sum_z (-1)^(x.z) |z>|f(x)>, with f computed
    directly from its boolean definition (y_i = x_i XOR (s_i AND x_j), j =
    lowest set bit of secret) rather than by simulating the primary's CNOTs.
    """
    j = (secret & -secret).bit_length() - 1
    dim = 2 ** (2 * n)
    vec = np.zeros(dim, dtype=complex)
    for x in range(2**n):
        f = 0
        for i in range(n):
            bit = (x >> i) & 1
            if (secret >> i) & 1:
                bit ^= (x >> j) & 1
            f |= bit << i
        for z in range(2**n):
            sign = (-1) ** bin(x & z).count("1")
            vec[z | (f << n)] += sign / (2**n)
    return Statevector(vec)


def _alt_grover(n: int, marked: list[int], iterations: int) -> Statevector:
    """Pure linear algebra: the diffuser as an explicit 2|s><s|-I matrix
    from the uniform-superposition outer product, and the oracle as an
    explicit diagonal — no gates (in particular, no MCX-based diffuser
    circuit) anywhere in this construction, unlike the primary's."""
    dim = 2**n
    s = np.full(dim, 1 / np.sqrt(dim))
    diffuser_matrix = 2 * np.outer(s, s) - np.eye(dim)
    oracle_diag = np.ones(dim, dtype=complex)
    for m in marked:
        oracle_diag[m] = -1
    psi = s.astype(complex)
    for _ in range(iterations):
        psi = oracle_diag * psi
        psi = diffuser_matrix @ psi
    return Statevector(psi)


def _alt_qpe(n_count: int, k: int) -> Statevector:
    """Closed-form target for an exactly-representable phase: the counting
    register lands on the single basis state |k>, eigenstate register on
    |1> — computed directly from the definition of phase estimation with a
    representable phase, not by simulating controlled-phase gates or an
    inverse QFT."""
    n_total = n_count + 1
    vec = np.zeros(2**n_total, dtype=complex)
    vec[k | (1 << n_count)] = 1.0
    return Statevector(vec)


def _alt_qaoa_maxcut(
    n: int, edges: list[tuple[int, int]], gamma: float, beta: float
) -> Statevector:
    """Cost layer applied as a single closed-form DIAGONAL phase (each basis
    state x gets phase exp(-i*gamma*cost(x)), cost(x) = sum over edges of
    (-1)^(x_i XOR x_j)) via `Diagonal` — a genuinely different construction
    from the primary's per-edge CX-RZ-CX decomposition, not just a
    relabeling of the same gates."""
    diag = []
    for x in range(2**n):
        cost = sum((-1) ** (((x >> i) & 1) ^ ((x >> j) & 1)) for i, j in edges)
        diag.append(np.exp(-1j * gamma * cost))
    qc = QuantumCircuit(n)
    qc.h(range(n))
    qc.append(Diagonal(diag), range(n))
    for q in range(n):
        qc.rx(2 * beta, q)
    return Statevector(qc)


def _zstring_eigenvalue(x: int, qubits: list[int]) -> int:
    parity = 0
    for q in qubits:
        parity ^= (x >> q) & 1
    return -1 if parity else 1


def _alt_diagonal_ising(
    n: int,
    field: dict[int, float],
    couplings: dict[tuple[int, int], float],
    higher_order: list[tuple[list[int], float]],
    gamma: float,
) -> QuantumCircuit:
    """T3 (D3f, research.md) — one shared closed-form alternative for all
    four T3 families: the diagonal phase computed directly from the cost
    function's own definition (field + pairwise + higher-order terms), via
    `Diagonal`, with NO CNOT ladder anywhere — a structurally different
    construction from the primary's CNOT-ladder-plus-RZ decomposition.
    """
    diag = []
    for x in range(2**n):
        cost = 0.0
        for qubit, h in field.items():
            cost += h * _zstring_eigenvalue(x, [qubit])
        for (i, j), coupling in couplings.items():
            cost += coupling * _zstring_eigenvalue(x, [i, j])
        for qubits, coeff in higher_order:
            cost += coeff * _zstring_eigenvalue(x, qubits)
        diag.append(np.exp(-1j * gamma * cost))
    qc = QuantumCircuit(n)
    qc.h(range(n))
    qc.append(Diagonal(diag), range(n))
    return qc


def _alt_ising_from_qubo(
    qubo: list[list[float]], n: int
) -> tuple[dict[int, float], dict[tuple[int, int], float]]:
    """Re-derivation of the QUBO -> Ising substitution, written independently
    of `build_t3_formulation.py`'s `ising_from_qubo` (same formula, no
    shared code) — both must agree for `qubo_ising_*` to pass check 2, which
    is exactly what makes this a genuine cross-check on the substitution
    itself, not just on the phase-circuit construction downstream of it.
    """
    field: dict[int, float] = dict.fromkeys(range(n), 0.0)
    couplings: dict[tuple[int, int], float] = {}
    for i in range(n):
        field[i] -= qubo[i][i] / 2
        for j in range(i + 1, n):
            qij = qubo[i][j]
            if qij == 0:
                continue
            field[i] -= qij / 4
            field[j] -= qij / 4
            couplings[(i, j)] = qij / 4
    return field, couplings


# task_id -> (alt, alt_circuit, is_library_primitive)
def _build_alternatives(
    task_id: str,
) -> tuple[Statevector | Operator, QuantumCircuit | None, bool]:
    """Returns (alt, alt_circuit, is_library). `alt` is a Statevector for
    oracle_kind="statevector" tasks, an Operator for "unitary" tasks.
    `alt_circuit` is a QuantumCircuit form of the SAME alternative — required
    for EVERY "unitary" task's round-trip sanity check (unconditional for
    that oracle_kind — see check_sanity_seeds), whether or not it happens to
    come from `qiskit.circuit.library`. It is None for every "statevector"
    task here: when a statevector-kind round-trip is needed (D3d/D3e —
    decided per task from the alternative's own measured peakedness, not
    hardcoded per family), `check_sanity_seeds` derives one generically from
    `alt` via `StatePreparation`, so no per-family circuit needs registering
    here. `is_library` is True only when `alt_circuit` is a genuine
    `qiskit.circuit.library` primitive (QFT) — that, not merely "a circuit
    form exists", is what `check_library_crosscheck` reports.
    """
    # T1 perturbed (T048) task_ids (exact matches) must be checked BEFORE the
    # generic "bell_"/"ghz_"/"w_state_"/"qft_" prefix branches below, which
    # would otherwise intercept e.g. "ghz_3q_perturbed" and mis-parse
    # "3q_perturbed" as a qubit count (same class of bug already found and
    # fixed once for T4's ghz_linear5_* task_ids).
    if task_id == "bell_phi_plus_2q_perturbed":
        return _alt_phase_bell(np.pi / 3), None, False
    if task_id == "ghz_3q_perturbed":
        return _alt_phase_ghz(3, 2 * np.pi / 5), None, False
    if task_id == "ghz_8q_perturbed":
        return _alt_phase_ghz(8, np.pi / 6), None, False
    if task_id == "w_state_3q_perturbed":
        return _alt_phase_w_state(3, 2, np.pi / 2), None, False
    if task_id == "bell_phi_minus_2q_perturbed":
        return Statevector(_alt_bell("phi_minus")), None, False
    if task_id == "ghz_5q_perturbed":
        return Statevector(_alt_ghz(5)), None, False
    if task_id == "reversible_half_adder_4q_perturbed":
        circuit = _alt_half_adder()
        return Operator(circuit), circuit, False
    if task_id == "w_state_5q_perturbed":
        return Statevector(_alt_w_state(5)), None, False
    if task_id == "dj_constant_4q_perturbed":
        return _alt_dj_reversed(3, None), None, False
    if task_id == "dj_balanced_6q_perturbed":
        return _alt_dj_reversed(5, 0b10110), None, False
    if task_id == "qft_8q_perturbed":
        circuit = _alt_qft_no_swap(8)
        return Operator(circuit), circuit, False
    if task_id == "reversible_full_adder_5q_perturbed":
        circuit = _alt_full_adder_reversed()
        return Operator(circuit), circuit, False
    if task_id == "bell_psi_plus_2q_perturbed":
        composed = _alt_compose_with_qft(_alt_bell("psi_plus"))
        return Statevector(composed), None, False
    if task_id == "w_state_8q_perturbed":
        composed = _alt_compose_with_qft(_alt_w_state(8))
        return Statevector(composed), None, False
    if task_id == "reversible_boolean4_8q_perturbed":
        circuit = _alt_compose_with_qft(_alt_boolean4())
        return Operator(circuit), circuit, False
    if task_id == "qft_3q_perturbed":
        lib = _alt_qft(3)
        return Operator(lib), lib, True
    if task_id == "qft_5q_perturbed":
        lib = _alt_qft(5)
        return Operator(lib), lib, True
    if task_id == "dj_balanced_4q_perturbed":
        return _alt_deutsch_jozsa(3, 0b101), None, False
    if task_id.startswith("bell_"):
        kind = task_id[len("bell_") : -len("_2q")]
        return Statevector(_alt_bell(kind)), None, False
    # T4's ghz_linear5_* task_ids (exact matches) must be checked BEFORE the
    # generic "ghz_" prefix branch below (T1's ghz_3q/5q/8q pattern), which
    # would otherwise intercept them and crash trying to int()-parse
    # "linear5_full" etc. as a qubit count.
    if task_id == "ghz_linear5_full":
        return _alt_ghz_subset(5, [0, 1, 2, 3, 4]), None, False
    if task_id == "ghz_linear5_scattered_even":
        return _alt_ghz_subset(5, [0, 2, 4]), None, False
    if task_id == "ghz_linear5_mixed":
        return _alt_ghz_subset(5, [0, 1, 4]), None, False
    if task_id == "ghz_linear5_endpoints":
        return _alt_ghz_subset(5, [0, 4]), None, False
    # T4 perturbed (T048) ghz_linear5_*_perturbed — same exact-match-before-
    # generic-prefix discipline as the canonical ghz_linear5_* block above.
    if task_id == "ghz_linear5_endpoints_perturbed":
        return _alt_ghz_subset(5, [0, 4]), None, False
    if task_id == "ghz_linear5_mixed_perturbed":
        return _alt_ghz_subset(5, [0, 1, 4]).reverse_qargs(), None, False
    if task_id == "ghz_linear5_scattered_even_perturbed":
        return _alt_ghz_subset(5, [0, 2, 4]), None, False
    if task_id == "ghz_linear5_full_perturbed":
        alt = _alt_ghz_subset(5, [0, 1, 2, 3, 4]).evolve(QFTGate(5), qargs=range(5))
        return alt, None, False
    if task_id.startswith("ghz_"):
        n = int(task_id[len("ghz_") : -1])
        return Statevector(_alt_ghz(n)), None, False
    if task_id.startswith("w_state_"):
        n = int(task_id[len("w_state_") : -1])
        return Statevector(_alt_w_state(n)), None, False
    if task_id.startswith("qft_"):
        n = int(task_id[len("qft_") : -1])
        lib = _alt_qft(n)
        return Operator(lib), lib, True
    if task_id == "dj_constant_4q":
        return _alt_deutsch_jozsa(3, None), None, False
    if task_id == "dj_balanced_4q":
        return _alt_deutsch_jozsa(3, 0b101), None, False
    if task_id == "dj_balanced_6q":
        return _alt_deutsch_jozsa(5, 0b10110), None, False
    if task_id == "reversible_half_adder_4q":
        circuit = _alt_half_adder()
        return Operator(circuit), circuit, False
    if task_id == "reversible_full_adder_5q":
        circuit = _alt_full_adder()
        return Operator(circuit), circuit, False
    if task_id == "reversible_boolean4_8q":
        circuit = _alt_boolean4()
        return Operator(circuit), circuit, False
    # T2 perturbed (T048) task_ids (exact matches) must be checked BEFORE
    # the generic "bv_"/"simon_" prefix branches below — same class of bug
    # already found and fixed once for T1's ghz_ prefix and again for T4's
    # ghz_linear5_* exact matches.
    if task_id == "bv_4q_perturbed":
        return _alt_bernstein_vazirani(3, 0b101), None, False
    if task_id == "grover_3q_perturbed":
        return _alt_grover(3, [5], 2), None, False
    if task_id == "qaoa_maxcut_3q_perturbed":
        return _alt_qaoa_maxcut(3, [(0, 1), (1, 2), (0, 2)], 0.5, 0.3), None, False
    if task_id == "bv_5q_perturbed":
        return _alt_bernstein_vazirani(4, 0b1011).reverse_qargs(), None, False
    if task_id == "simon_8q_perturbed":
        return _alt_simon(4, 0b1010).reverse_qargs(), None, False
    if task_id == "qpe_4q_perturbed":
        return _alt_qpe(3, 3).reverse_qargs(), None, False
    if task_id == "grover_5q_perturbed":
        return _alt_grover(5, [13, 20], 3).reverse_qargs(), None, False
    if task_id == "bv_6q_perturbed":
        return _alt_bernstein_vazirani(5, 0b10110), None, False
    if task_id == "simon_10q_perturbed":
        return _alt_simon(5, 0b10110), None, False
    if task_id == "qpe_5q_perturbed":
        return _alt_qpe(4, 5), None, False
    if task_id == "simon_6q_perturbed":
        alt = _alt_simon(3, 0b101).evolve(RZGate(np.pi / 4), qargs=[0])
        return alt, None, False
    if task_id == "grover_4q_perturbed":
        alt = _alt_grover(4, [9], 3).evolve(RZGate(np.pi / 4), qargs=[0])
        return alt, None, False
    if task_id == "qaoa_maxcut_4q_perturbed":
        base = _alt_qaoa_maxcut(4, [(0, 1), (1, 2), (2, 3), (3, 0)], 0.6, 0.4)
        return base.evolve(RZGate(np.pi / 4), qargs=[0]), None, False
    if task_id == "qpe_6q_perturbed":
        alt = _alt_qpe(5, 11).evolve(QFTGate(6), qargs=range(6))
        return alt, None, False
    if task_id == "qaoa_maxcut_5q_perturbed":
        base = _alt_qaoa_maxcut(5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)], 0.7, 0.35)
        return base.evolve(QFTGate(5), qargs=range(5)), None, False
    if task_id.startswith("bv_"):
        n_input = int(task_id[len("bv_") : -1]) - 1
        secret = {"bv_4q": 0b101, "bv_5q": 0b1011, "bv_6q": 0b10110}[task_id]
        return _alt_bernstein_vazirani(n_input, secret), None, False
    if task_id.startswith("simon_"):
        n = int(task_id[len("simon_") : -1]) // 2
        secret = {"simon_6q": 0b101, "simon_8q": 0b1010, "simon_10q": 0b10110}[task_id]
        return _alt_simon(n, secret), None, False
    if task_id == "grover_3q":
        return _alt_grover(3, [5], 2), None, False
    if task_id == "grover_4q":
        return _alt_grover(4, [9], 3), None, False
    if task_id == "grover_5q":
        return _alt_grover(5, [13, 20], 3), None, False
    if task_id == "qpe_4q":
        return _alt_qpe(3, 3), None, False
    if task_id == "qpe_5q":
        return _alt_qpe(4, 5), None, False
    if task_id == "qpe_6q":
        return _alt_qpe(5, 11), None, False
    if task_id == "qaoa_maxcut_3q":
        return _alt_qaoa_maxcut(3, [(0, 1), (1, 2), (0, 2)], 0.5, 0.3), None, False
    if task_id == "qaoa_maxcut_4q":
        return _alt_qaoa_maxcut(4, [(0, 1), (1, 2), (2, 3), (3, 0)], 0.6, 0.4), None, False
    if task_id == "qaoa_maxcut_5q":
        edges = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)]
        return _alt_qaoa_maxcut(5, edges, 0.7, 0.35), None, False
    # T3 perturbed (T048) task_ids — all exact matches, no prefix-collision
    # risk (T3's task_ids never share a prefix with a differently-parsed
    # family), but grouped here as a block for the same reason T1/T2's
    # perturbed dispatches are grouped: keeps the "same discipline, per
    # tier" structure legible.
    if task_id == "ising_weighted_maxcut_3q_perturbed":
        c = _alt_diagonal_ising(3, {}, {(0, 1): 0.6, (1, 2): -0.4, (0, 2): 0.9}, [], 0.5)
        c = c.copy()
        c.rz(np.pi / 4, 0)
        return Operator(c), c, False
    if task_id == "ising_field_coupling_4q_perturbed":
        field = {0: 0.2, 1: -0.4, 2: 0.3, 3: 0.1}
        couplings = {(0, 1): 0.5, (2, 3): 0.3}
        c = _alt_diagonal_ising(4, field, couplings, [], 0.45)
        c = c.copy()
        c.rz(np.pi / 4, 0)
        return Operator(c), c, False
    if task_id == "ising_weighted_maxcut_4q_perturbed":
        couplings = {(0, 1): 0.3, (1, 2): 0.7, (2, 3): -0.5, (0, 3): 0.4}
        c = _alt_diagonal_ising(4, {}, couplings, [], 0.45)
        return Operator(c), c, False
    if task_id == "ising_mixed_body_4q_perturbed":
        c = _alt_diagonal_ising(4, {}, {}, [([0, 1], 0.4), ([1, 2, 3], 0.6)], 0.5)
        return Operator(c), c, False
    if task_id == "qubo_ising_3var_perturbed":
        field, couplings = _alt_ising_from_qubo([[2, -1, 0.5], [0, -3, 1.5], [0, 0, 1]], 3)
        c = _alt_diagonal_ising(3, field, couplings, [], 0.5)
        return Operator(c), c, False
    if task_id == "ising_weighted_maxcut_5q_perturbed":
        couplings = {(0, 1): 0.5, (0, 2): -0.3, (0, 3): 0.8, (0, 4): 0.2}
        c = _alt_diagonal_ising(5, {}, couplings, [], 0.4).reverse_bits()
        return Operator(c), c, False
    if task_id == "ising_field_coupling_3q_perturbed":
        c = _alt_diagonal_ising(3, {0: 0.3, 1: 0.5, 2: -0.2}, {(0, 1): 0.4}, [], 0.5).reverse_bits()
        return Operator(c), c, False
    if task_id == "qubo_ising_4var_perturbed":
        qubo = [[1.5, -0.8, 0.6, 0.0], [0, -2.0, 0.4, 0.9], [0, 0, 1.0, -0.7], [0, 0, 0, 0.5]]
        field, couplings = _alt_ising_from_qubo(qubo, 4)
        c = _alt_diagonal_ising(4, field, couplings, [], 0.45).reverse_bits()
        return Operator(c), c, False
    if task_id == "ising_zzz_3q_perturbed":
        c = _alt_diagonal_ising(3, {}, {}, [([0, 1, 2], 0.7)], 3 / 5)
        return Operator(c), c, False
    if task_id == "qubo_ising_5var_perturbed":
        qubo = [
            [1.0, 0.5, -0.6, 0.0, 0.3],
            [0, -1.5, 0.8, -0.4, 0.0],
            [0, 0, 1.2, 0.5, -0.3],
            [0, 0, 0, -0.8, 0.6],
            [0, 0, 0, 0, 0.4],
        ]
        field, couplings = _alt_ising_from_qubo(qubo, 5)
        c = _alt_diagonal_ising(5, field, couplings, [], 2 / 5)
        return Operator(c), c, False
    if task_id == "ising_zzzz_4q_perturbed":
        c = _alt_diagonal_ising(4, {}, {}, [([0, 1, 2, 3], 0.5)], 0.5)
        c = c.copy()
        c.append(QFTGate(4), range(4))
        return Operator(c), c, False
    if task_id == "ising_field_coupling_5q_perturbed":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        c = c.copy()
        c.append(QFTGate(5), range(5))
        return Operator(c), c, False
    if task_id == "ising_weighted_maxcut_3q":
        c = _alt_diagonal_ising(3, {}, {(0, 1): 0.6, (1, 2): -0.4, (0, 2): 0.9}, [], 0.5)
        return Operator(c), c, False
    if task_id == "ising_weighted_maxcut_4q":
        couplings = {(0, 1): 0.3, (1, 2): 0.7, (2, 3): -0.5, (0, 3): 0.4}
        c = _alt_diagonal_ising(4, {}, couplings, [], 0.45)
        return Operator(c), c, False
    if task_id == "ising_weighted_maxcut_5q":
        couplings = {(0, 1): 0.5, (0, 2): -0.3, (0, 3): 0.8, (0, 4): 0.2}
        c = _alt_diagonal_ising(5, {}, couplings, [], 0.4)
        return Operator(c), c, False
    if task_id == "ising_zzz_3q":
        c = _alt_diagonal_ising(3, {}, {}, [([0, 1, 2], 0.7)], 0.6)
        return Operator(c), c, False
    if task_id == "ising_zzzz_4q":
        c = _alt_diagonal_ising(4, {}, {}, [([0, 1, 2, 3], 0.5)], 0.5)
        return Operator(c), c, False
    if task_id == "ising_mixed_body_4q":
        c = _alt_diagonal_ising(4, {}, {}, [([0, 1], 0.4), ([1, 2, 3], 0.6)], 0.5)
        return Operator(c), c, False
    if task_id == "ising_field_coupling_3q":
        c = _alt_diagonal_ising(3, {0: 0.3, 1: 0.5, 2: -0.2}, {(0, 1): 0.4}, [], 0.5)
        return Operator(c), c, False
    if task_id == "ising_field_coupling_4q":
        field = {0: 0.2, 1: -0.4, 2: 0.3, 3: 0.1}
        couplings = {(0, 1): 0.5, (2, 3): 0.3}
        c = _alt_diagonal_ising(4, field, couplings, [], 0.45)
        return Operator(c), c, False
    if task_id == "ising_field_coupling_5q":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        return Operator(c), c, False
    if task_id == "qubo_ising_3var":
        field, couplings = _alt_ising_from_qubo([[2, -1, 0.5], [0, -3, 1.5], [0, 0, 1]], 3)
        c = _alt_diagonal_ising(3, field, couplings, [], 0.5)
        return Operator(c), c, False
    if task_id == "qubo_ising_4var":
        qubo = [[1.5, -0.8, 0.6, 0.0], [0, -2.0, 0.4, 0.9], [0, 0, 1.0, -0.7], [0, 0, 0, 0.5]]
        field, couplings = _alt_ising_from_qubo(qubo, 4)
        c = _alt_diagonal_ising(4, field, couplings, [], 0.45)
        return Operator(c), c, False
    if task_id == "qubo_ising_5var":
        qubo = [
            [1.0, 0.5, -0.6, 0.0, 0.3],
            [0, -1.5, 0.8, -0.4, 0.0],
            [0, 0, 1.2, 0.5, -0.3],
            [0, 0, 0, -0.8, 0.6],
            [0, 0, 0, 0, 0.4],
        ]
        field, couplings = _alt_ising_from_qubo(qubo, 5)
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        return Operator(c), c, False
    # T4 perturbed (T048) — exact matches, grouped as a block (same reason
    # as T3's equivalent block above).
    if task_id == "ising_linear5_distance2_perturbed":
        edge_weights = {(0, 2): 0.5, (1, 3): -0.4, (2, 4): 0.3}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.45)
        c = c.copy()
        c.rz(np.pi / 4, 0)
        return Operator(c), c, False
    if task_id == "zstring_linear5_scattered_perturbed":
        c = _alt_diagonal_ising(5, {}, {}, [([0, 2, 4], 0.6)], 0.5)
        c = c.copy()
        c.rz(np.pi / 4, 0)
        return Operator(c), c, False
    if task_id == "ising_linear5_endpoints_perturbed":
        c = _alt_diagonal_ising(5, {}, {(0, 4): 0.6}, [], 0.5)
        return Operator(c), c, False
    if task_id == "field_coupling_linear5_local_perturbed":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        return Operator(c), c, False
    if task_id == "ising_linear5_local_perturbed":
        edge_weights = {(0, 1): 0.4, (1, 2): -0.3, (2, 3): 0.5, (3, 4): -0.2}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.5).reverse_bits()
        return Operator(c), c, False
    if task_id == "field_coupling_linear5_scattered_perturbed":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 4): 0.4, (1, 3): -0.3}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4).reverse_bits()
        return Operator(c), c, False
    if task_id == "zstring_linear5_full_chain_perturbed":
        c = _alt_diagonal_ising(5, {}, {}, [([0, 1, 2, 3, 4], 1 / 2)], 1 / 2)
        return Operator(c), c, False
    if task_id == "ising_linear5_mixed_perturbed":
        edge_weights = {(0, 1): 0.3, (2, 3): -0.4, (0, 4): 0.5}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.45)
        c = c.copy()
        c.append(QFTGate(5), range(5))
        return Operator(c), c, False
    if task_id == "ising_linear5_local":
        edge_weights = {(0, 1): 0.4, (1, 2): -0.3, (2, 3): 0.5, (3, 4): -0.2}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.5)
        return Operator(c), c, False
    if task_id == "ising_linear5_distance2":
        edge_weights = {(0, 2): 0.5, (1, 3): -0.4, (2, 4): 0.3}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.45)
        return Operator(c), c, False
    if task_id == "ising_linear5_endpoints":
        c = _alt_diagonal_ising(5, {}, {(0, 4): 0.6}, [], 0.5)
        return Operator(c), c, False
    if task_id == "ising_linear5_mixed":
        edge_weights = {(0, 1): 0.3, (2, 3): -0.4, (0, 4): 0.5}
        c = _alt_diagonal_ising(5, {}, edge_weights, [], 0.45)
        return Operator(c), c, False
    if task_id == "zstring_linear5_scattered":
        c = _alt_diagonal_ising(5, {}, {}, [([0, 2, 4], 0.6)], 0.5)
        return Operator(c), c, False
    if task_id == "zstring_linear5_full_chain":
        c = _alt_diagonal_ising(5, {}, {}, [([0, 1, 2, 3, 4], 0.5)], 0.5)
        return Operator(c), c, False
    if task_id == "field_coupling_linear5_scattered":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 4): 0.4, (1, 3): -0.3}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        return Operator(c), c, False
    if task_id == "field_coupling_linear5_local":
        field = {0: 0.2, 1: 0.3, 2: -0.1, 3: 0.4, 4: -0.3}
        couplings = {(0, 1): 0.3, (1, 2): 0.4, (2, 3): -0.2, (3, 4): 0.5}
        c = _alt_diagonal_ising(5, field, couplings, [], 0.4)
        return Operator(c), c, False
    raise KeyError(
        f"no registered independent construction for task_id={task_id!r} — "
        "add one to bench/validate_oracles.py before shipping this task"
    )


def check_property(task: TaskSpec, primary: QuantumCircuit) -> tuple[bool, str]:
    if task.oracle_kind == "unitary":
        u = Operator(primary).data
        is_unitary = np.allclose(u @ u.conj().T, np.eye(u.shape[0]), atol=1e-8)
        return is_unitary, "U @ U^dagger ≈ I" if is_unitary else "U @ U^dagger != I"
    norm = float(np.linalg.norm(Statevector(primary).data))
    ok = abs(norm - 1.0) < 1e-8
    return ok, f"||psi|| = {norm:.10f}"


def check_alternative_construction(task: TaskSpec, primary: QuantumCircuit) -> tuple[bool, str]:
    alt, _, _ = _build_alternatives(task.task_id)
    if task.oracle_kind == "unitary":
        equivalent = Operator(primary).equiv(alt)
    else:
        equivalent = Statevector(primary).equiv(alt)
    return equivalent, "primary and independent alternative agree" if equivalent else "DISAGREE"


def check_library_crosscheck(task: TaskSpec, primary: QuantumCircuit) -> tuple[bool | None, str]:
    _, alt_circuit, is_library = _build_alternatives(task.task_id)
    if not is_library:
        return None, "N/A — no qiskit.circuit.library primitive for this family"
    assert alt_circuit is not None, "is_library=True must always carry a circuit"
    equivalent = Operator(primary).equiv(Operator(alt_circuit))
    return equivalent, "matches qiskit.circuit.library" if equivalent else "DISAGREE"


def check_sanity_seeds(task: TaskSpec, primary: QuantumCircuit) -> tuple[bool, str]:
    """Real AerSimulator run (seeds 1/2/3), measured counts compared via
    Hellinger fidelity against a target derived INDEPENDENTLY of `primary`
    — from the alternative construction (`_build_alternatives`), never from
    `primary` itself. Deriving "expected" from `primary` (an earlier version
    of this function did) only tests "does the simulator faithfully execute
    what the circuit specifies" — never "is the circuit's specification
    correct". That correctness question is checks 1-2's job, answered
    exactly (zero sampling noise) via Operator.equiv/Statevector.equiv; this
    check cannot substitute for them and is not calibrated as if it could.

    `oracle_kind="unitary"` needs one more fix beyond that substitution: QFT
    maps ANY computational-basis input to a UNIFORM-MAGNITUDE output — that
    is what a Fourier transform of a delta function IS, correct or not. A
    single dropped controlled-phase gate, or even computing the INVERSE QFT
    throughout, still measures as exactly uniform — comparing measured
    counts against `Statevector(prep + primary)` (the original design) is
    blind to any purely-phase bug BY CONSTRUCTION, independent of tolerance
    (verified: a circuit computing the inverse QFT instead of QFT measured
    Hellinger fidelity 1.0000 against that target — indistinguishable from
    correct). Composing `primary` with the independent alternative's INVERSE
    fixes this: if `primary` is correct, `primary` -> `alt^-1` returns
    exactly to the input state — a SHARP, measurement-distinguishable
    target — and any phase divergence between `primary` and `alt` now leaks
    measured probability away from it. Verified against real bugs: the
    inverse-QFT bug above now reads 0.0000 (was indistinguishable from
    correct); a single dropped controlled-phase gate reads 0.9999 — not
    clearly below any practical threshold, since it perturbs only one very
    small angle. That residual insensitivity to a single-gate error is
    expected and accepted, not a gap to close here: catching it exactly is
    checks 1-2's job (Operator.equiv() rejects the same dropped-gate circuit
    unconditionally, not probabilistically), and this check's own role (per
    the module docstring) is real-simulation/transpilation sanity, not a
    second, weaker copy of construction-correctness.

    D3e (research.md): the QFT finding above generalizes — the round-trip is
    the right design whenever the target distribution is spread, not only
    when the oracle happens to be `oracle_kind="unitary"`. `oracle_kind=
    "unitary"` tasks (a general transform, no single natural "target
    distribution" to be peaked or not about) are ALWAYS round-tripped, as
    before. `oracle_kind="statevector"` tasks are round-tripped whenever the
    alternative's own measured max outcome probability falls below
    `PEAKEDNESS_THRESHOLD` — computed per task, not decided per family. When
    a statevector-kind round-trip is needed, the round-trip target circuit
    is derived generically via `StatePreparation(alt.data)`: since `alt` is
    already independent of `primary` by construction, this is NOT the
    tautological "primary composed with its own inverse" trap — composing
    `primary` with a DIFFERENT valid preparation's inverse still cancels to
    the origin only if `primary` reaches the same target `alt` does.
    """
    alt, alt_circuit, _ = _build_alternatives(task.task_id)

    if task.oracle_kind == "unitary":
        if alt_circuit is None:
            raise NotImplementedError(
                f"{task.task_id}: oracle_kind='unitary' sanity check needs an "
                "independent alternative CIRCUIT (not just an Operator) to "
                "round-trip against — see this function's docstring. Expose "
                "one via _build_alternatives before shipping this task."
            )
        prep = QuantumCircuit(primary.num_qubits)
        prep.x(0)  # any non-|0...0> input works — it only needs to be sharp
        full = prep.compose(primary).compose(alt_circuit.inverse())
        expected = Statevector(prep).probabilities_dict(decimals=10)
    else:
        prep = QuantumCircuit(primary.num_qubits)  # statevector oracles ARE defined from |0...0>
        direct_expected = alt.probabilities_dict(decimals=10)  # alt: Statevector here
        peak = max(direct_expected.values())
        if peak >= PEAKEDNESS_THRESHOLD:
            full = prep.compose(primary)
            expected = direct_expected
        else:
            alt_prep = QuantumCircuit(primary.num_qubits)
            alt_prep.append(StatePreparation(alt.data), range(primary.num_qubits))
            full = prep.compose(primary).compose(alt_prep.inverse())
            expected = Statevector(prep).probabilities_dict(decimals=10)

    measured = full.copy()
    measured.measure_all()
    # StatePreparation (and, worse, its INVERSE — the round-trip path above)
    # decomposes into "multiplexer" instructions that crash Aer with a
    # SEGFAULT (not a Python exception) if handed to transpile() undecomposed
    # — reproduced directly: transpile() alone accepted the circuit and
    # reported no error, then `sim.run()` on the result crashed the process.
    # Pre-unrolling to standard gates before transpile() avoids it; verified
    # this does not change the measured circuit's behavior (transpile()'s
    # basis-gate translation is unaffected by whether the decomposition
    # happened once here or once for us inside transpile()).
    measured = measured.decompose(reps=8)

    fidelities = []
    for seed in SANITY_SEEDS:
        sim = make_simulator(full.num_qubits, seed=seed)
        transpiled = transpile(measured, sim, seed_transpiler=seed)
        result = sim.run(transpiled, shots=SANITY_SHOTS).result()
        counts = result.get_counts()
        fidelities.append(hellinger_fidelity(counts, expected))

    mean_fid = float(np.mean(fidelities))
    ok = mean_fid >= SANITY_FIDELITY_MIN
    return ok, f"mean Hellinger fidelity over {len(SANITY_SEEDS)} seeds = {mean_fid:.4f}"


# -- oracle_kind="energy" (VQE H2, D3e) — structurally different from every
# other family here: the oracle is a Hamiltonian + its ground energy, not a
# circuit, so it gets its own 4-check implementation rather than reusing
# check_property/check_alternative_construction/check_sanity_seeds above.

_PAULI_MATRICES = {
    "I": np.array([[1, 0], [0, 1]], dtype=complex),
    "X": np.array([[0, 1], [1, 0]], dtype=complex),
    "Y": np.array([[0, -1j], [1j, 0]], dtype=complex),
    "Z": np.array([[1, 0], [0, -1]], dtype=complex),
}

ENERGY_SANITY_TOL = 0.02  # Hartree; see check_energy_sanity_seeds docstring


def _label_to_matrix(label: str) -> np.ndarray:
    """Builds a Pauli string's matrix via raw Kronecker products — no
    `SparsePauliOp.to_matrix()` anywhere in this function, so it shares no
    code with how the primary Hamiltonian's matrix gets built for checks 1
    and the ansatz's expectation-value computation."""
    matrices = [_PAULI_MATRICES[ch] for ch in label]
    result = matrices[0]
    for m in matrices[1:]:
        result = np.kron(result, m)
    return result


def check_energy_property(payload: dict) -> tuple[bool, str]:
    hamiltonian = SparsePauliOp(payload["pauli_labels"], coeffs=payload["coeffs"])
    matrix = hamiltonian.to_matrix()
    hermitian = bool(np.allclose(matrix, matrix.conj().T, atol=1e-10))
    return hermitian, "H == H^dagger" if hermitian else "H != H^dagger"


def check_energy_alternative(payload: dict) -> tuple[bool, str]:
    """Independent construction: the Hamiltonian matrix built from raw
    Kronecker products (`_label_to_matrix`, never `SparsePauliOp.
    to_matrix()`), diagonalized via `scipy.sparse.linalg.eigsh` (an
    iterative Lanczos-type method) — a different matrix-construction path
    AND a different diagonalization algorithm than `numpy.linalg.eigh` on
    `SparsePauliOp.to_matrix()`, which is how `exact_ground_energy` was
    produced when the oracle file was built.
    """
    matrix = sum(
        c * _label_to_matrix(label)
        for c, label in zip(payload["coeffs"], payload["pauli_labels"], strict=True)
    )
    eigenvalue = eigsh(csr_matrix(matrix), k=1, which="SA")[0][0]
    stored = payload["exact_ground_energy"]
    agree = abs(float(eigenvalue) - stored) < 1e-8
    detail = f"eigsh ground energy = {eigenvalue:.10f} vs stored {stored:.10f}"
    return agree, detail if agree else f"DISAGREE: {detail}"


def check_energy_sanity_seeds(payload: dict) -> tuple[bool, str]:
    """Real AerSimulator run of the task's OWN cited ansatz
    (`ansatz_theta_rad`, X + RY + CX — see build_t2_vqe_h2.py), estimating
    <H> by measuring in three bases (Z-basis directly gives the I/IZ/ZI/ZZ
    terms; H on both qubits before measuring gives the XX term; Sdg+H on
    both qubits gives the YY term — the standard basis-rotation recipe for
    estimating a Pauli expectation value from computational-basis counts),
    then comparing the shot-weighted estimate against `exact_ground_energy`.

    `ENERGY_SANITY_TOL=0.02` (Hartree) is calibrated the same way
    `SANITY_FIDELITY_MIN` was: Monte Carlo at the real shot count (8192,
    same seeds convention), 10 trials on this Hamiltonian's own ansatz,
    gave std~0.0029 and a worst observed error of ~0.006 — 0.02 leaves
    ~3x that margin, so it will not fail a genuinely correct ansatz to
    shot noise alone.

    Ansatz qubit roles (which qubit gets X, which gets RY, CX control/
    target) are read from the payload with the canonical defaults
    (0, 1, 1, 0) — T048's `vqe_h2_r130_perturbed` (qubit-ordering family)
    is the only payload that overrides them, swapping roles to match its
    swapped Z0/Z1 Hamiltonian coefficients (build_t2_perturbed.py).
    """
    labels = payload["pauli_labels"]
    coeffs = dict(zip(labels, payload["coeffs"], strict=True))
    theta = payload["ansatz_theta_rad"]
    x_qubit = payload.get("ansatz_x_qubit", 0)
    ry_qubit = payload.get("ansatz_ry_qubit", 1)
    cx_control = payload.get("ansatz_cx_control", 1)
    cx_target = payload.get("ansatz_cx_target", 0)

    def ansatz() -> QuantumCircuit:
        qc = QuantumCircuit(2)
        qc.x(x_qubit)
        qc.ry(theta, ry_qubit)
        qc.cx(cx_control, cx_target)
        return qc

    def eigenvalue_for(label: str, bitstring: str) -> int:
        value = 1
        for i, ch in enumerate(reversed(bitstring)):
            if label[len(label) - 1 - i] != "I" and ch == "1":
                value *= -1
        return value

    groups: dict[str, list[str]] = {"Z": [], "X": [], "Y": []}
    for label in labels:
        if label == "II":
            continue  # constant term, added directly below
        if any(ch == "X" for ch in label):
            groups["X"].append(label)
        elif any(ch == "Y" for ch in label):
            groups["Y"].append(label)
        else:
            groups["Z"].append(label)

    estimates = []
    for seed in SANITY_SEEDS:
        total = coeffs.get("II", 0.0)
        for basis, group_labels in groups.items():
            if not group_labels:
                continue
            qc = ansatz()
            if basis == "X":
                qc.h(0)
                qc.h(1)
            elif basis == "Y":
                qc.sdg(0)
                qc.h(0)
                qc.sdg(1)
                qc.h(1)
            qc.measure_all()
            sim = make_simulator(2, seed=seed)
            transpiled = transpile(qc, sim, seed_transpiler=seed)
            counts = sim.run(transpiled, shots=SANITY_SHOTS).result().get_counts()
            for label in group_labels:
                expectation = (
                    sum(eigenvalue_for(label, bs) * count for bs, count in counts.items())
                    / SANITY_SHOTS
                )
                total += coeffs[label] * expectation
        estimates.append(total)

    mean_energy = float(np.mean(estimates))
    exact = payload["exact_ground_energy"]
    error = abs(mean_energy - exact)
    ok = error <= ENERGY_SANITY_TOL
    detail = (
        f"mean measured energy over {len(SANITY_SEEDS)} seeds = {mean_energy:.4f} Ha "
        f"(exact {exact:.4f}, error {error:.4f})"
    )
    return ok, detail


def validate_energy_oracle(task: TaskSpec) -> list[tuple[str, bool | None, str]]:
    with open(task.oracle_path) as f:
        payload = json.load(f)
    return [
        ("hermiticidade", *check_energy_property(payload)),
        ("construção alternativa", *check_energy_alternative(payload)),
        (
            "cross-check com biblioteca",
            None,
            "N/A — no qiskit.circuit.library primitive for this family",
        ),
        ("sanity em 3 seeds", *check_energy_sanity_seeds(payload)),
    ]


def validate_one(task: TaskSpec) -> list[tuple[str, bool | None, str]]:
    if task.oracle_kind == "energy":
        return validate_energy_oracle(task)

    with open(task.oracle_path, "rb") as f:
        (primary,) = qpy.load(f)

    results = [
        ("unitariedade/normalização", *check_property(task, primary)),
        ("construção alternativa", *check_alternative_construction(task, primary)),
        ("cross-check com biblioteca", *check_library_crosscheck(task, primary)),
        ("sanity em 3 seeds", *check_sanity_seeds(task, primary)),
    ]
    return results


def check_perturbation_pairing(all_tasks: list[TaskSpec]) -> list[tuple[str, bool | None, str]]:
    """FR-017: every canonical task must have exactly one paired perturbed
    variant, linked via `base_task_id`. Two invariants are ALWAYS enforced
    (blocking, regardless of how much of T048 is built): no perturbed task
    may reference a missing or itself-perturbed base_task_id, and no
    canonical task may have more than one perturbed variant. The
    COMPLETENESS invariant — every canonical task has AT LEAST one variant —
    is reported but not yet blocking while T048 is built incrementally
    (T1's 18 first, reviewed, then T2-T4); it becomes a hard failure
    automatically once every canonical task has a variant, so this gate
    tightens on its own as the dataset completes rather than needing a
    manual flip later.
    """
    canonical_ids = {t.task_id for t in all_tasks if not t.perturbed}
    perturbed = [t for t in all_tasks if t.perturbed]
    results: list[tuple[str, bool | None, str]] = []
    base_to_variants: dict[str, list[str]] = {}
    for t in perturbed:
        if t.base_task_id is None:
            results.append((t.task_id, False, "perturbed=True but base_task_id is not set"))
            continue
        if t.base_task_id not in canonical_ids:
            results.append(
                (
                    t.task_id,
                    False,
                    f"base_task_id={t.base_task_id!r} does not reference an "
                    "existing non-perturbed task",
                )
            )
            continue
        base_to_variants.setdefault(t.base_task_id, []).append(t.task_id)
    for base_id, variants in base_to_variants.items():
        if len(variants) > 1:
            results.append(
                (
                    base_id,
                    False,
                    f"has {len(variants)} perturbed variants {variants} — "
                    "FR-017 requires exactly one",
                )
            )
    n_paired = len(base_to_variants)
    n_canonical = len(canonical_ids)
    if n_canonical > 0 and n_paired == n_canonical:
        results.append(
            (
                "<pairing coverage>",
                True,
                f"all {n_canonical} canonical tasks have exactly one paired perturbed variant",
            )
        )
    else:
        results.append(
            (
                "<pairing coverage>",
                None,
                f"{n_paired}/{n_canonical} canonical tasks have a paired "
                "perturbed variant so far (T048 in progress)",
            )
        )
    return results


def main() -> None:
    task_paths = sorted(TASKS_DIR.rglob("*.json"))
    if not task_paths:
        print(f"no task files found under {TASKS_DIR}/", file=sys.stderr)
        raise SystemExit(1)

    all_tasks = [TaskSpec.model_validate_json(path.read_text()) for path in task_paths]

    any_failed = False
    for task in all_tasks:
        print(
            f"\n{task.task_id} ({task.tier}, oracle_kind={task.oracle_kind}, "
            f"n_qubits={task.n_qubits})"
        )
        for name, verdict, detail in validate_one(task):
            if verdict is None:
                status = "N/A "
            elif verdict:
                status = "PASS"
            else:
                status = "FAIL"
                any_failed = True
            print(f"  [{status}] {name}: {detail}")

    print("\nperturbation pairing (FR-017)")
    for name, verdict, detail in check_perturbation_pairing(all_tasks):
        if verdict is None:
            status = "INFO"
        elif verdict:
            status = "PASS"
        else:
            status = "FAIL"
            any_failed = True
        print(f"  [{status}] {name}: {detail}")

    print("\n" + "=" * 70)
    print("ALL ORACLES PASSED" if not any_failed else "AT LEAST ONE ORACLE FAILED")
    if any_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
