"""Builds the reference (oracle) circuits/payloads for T2's 18 perturbed
variants (T048, T049) — one per T2 canonical task (FR-017), task_id =
`<base>_perturbed`, `base_task_id` set to the canonical's task_id.

    uv run python -m bench.oracles.build_t2_perturbed

Five families (D12), same discipline as T1 (build_t1_perturbed.py) — but T2's
tasks are algorithms, not state-prep primitives, so which family is a
GENUINE perturbation (same task, harder to memorize) versus a task-identity
change had to be checked per instance, not assumed from the family name
alone. Three checks, done BEFORE any assignment below, are recorded here so
a future reader does not have to re-derive them:

  1. **Qubit-ordering can be a silent no-op.** `.reverse_bits()` only
     perturbs anything if the target is not itself symmetric under full
     qubit reversal. Checked computationally against every candidate's
     canonical `.qpy` (`Statevector.equiv(Statevector.reverse_qargs())`)
     before assignment — same class of check T1 already needed for GHZ/
     W-state (permutation-symmetric), but with TWO new failure shapes found
     here: `grover_3q`/`grover_4q`'s marked bitstrings (101, 1001) are
     palindromes, so reversal maps the marked value to itself and the whole
     circuit (oracle depends only on the marked INTEGER, diffuser is fully
     qubit-permutation-symmetric) is invariant; and — more strikingly —
     ALL THREE `qaoa_maxcut_*` graphs (triangle, 4-cycle, 5-cycle) are
     invariant under full reversal, because every cycle graph C_n has the
     reflection i -> n-1-i as a graph automorphism (a structural fact about
     cycles, not a coincidence of these three instances) — so
     qubit-ordering is EXCLUDED from the QAOA family entirely here, not
     used for even one of its three instances. `qpe_5q`'s counting/
     eigenstate split also happened to be reversal-symmetric (verified,
     not an obvious a priori fact the way the graph case is) — excluded
     too, one QPE instance moved to symbolic-parameterization instead.
  2. **Relative phase is vacuous on a fully deterministic target.**
     Bernstein-Vazirani's and QPE's targets collapse to a SINGLE
     computational basis state (up to the fixed |-> ancilla for BV) — an
     RZ on any qubit of a single-basis-state register is pure global phase,
     invisible to `Statevector.equiv()`, which is explicitly global-phase
     tolerant. Relative-phase is therefore restricted to families whose
     target is a genuine multi-term superposition: Simon (verified — its
     final state is a sum over multiple z-register basis states with
     nontrivial relative signs), Grover (amplified but not fully
     concentrated at these sizes), and QAOA (cost-weighted superposition
     over all 2^n bitstrings). Checked computationally (not assumed) for
     one instance of each before use.
  3. **Gate-set restriction to {rz, sx, x, cx} appears to silently break on
     SWAP + this specific combination at optimization_level >= 2 — but is
     NOT a transpiler bug** (research.md D3k has the full investigation,
     done after this same shape appeared once already in T1's build): it is
     `TranspileLayout.final_layout`, documented, intentional behavior —
     without a `coupling_map`, `optimization_level>=2` may implement a
     logical SWAP purely by relabeling which output position corresponds to
     which input qubit, recording that permutation in `final_layout` instead
     of emitting a physical SWAP gate. `Operator(transpiled)` ignores that
     metadata (hence the ~1e-32 fidelity, not "close to 1" — a completely
     wrong-LOOKING circuit); `Operator.from_circuit(transpiled)` (which
     reads `final_layout`) agrees exactly. Minimal reproducer: a bare 2-qubit
     `QuantumCircuit.swap(0,1)` transpiled to this basis at opt_level=2
     already exhibits it (Qiskit 1.2.4) — confirmed NOT a reportable issue,
     it's the documented purpose of `TranspileLayout`/`Operator.
     from_circuit`. Gate-set restriction is still excluded from all three
     QPE instances here — not because the transpiler is wrong, but because
     `validate_oracles.py`'s equivalence checks use plain `Operator()`
     throughout, and extending them to be layout-aware for this one case was
     out of scope this round. A future gate-set-restriction task on a
     circuit containing a SWAP, with `optimization_level>=2` and no
     `coupling_map`, should use `Operator.from_circuit()`, not re-open this
     investigation.

Family assignment (18 tasks, checked individually against the three traps
above): gate-set-restriction (4: bv_4q, grover_3q, qaoa_maxcut_3q,
vqe_h2_r055), qubit-ordering (5: bv_5q, simon_8q, qpe_4q, grover_5q,
vqe_h2_r130), symbolic-parameterization (4: bv_6q, simon_10q, qpe_5q,
vqe_h2_r075), relative-phase (3: simon_6q, grover_4q, qaoa_maxcut_4q),
composition (2: qpe_6q, qaoa_maxcut_5q).

For every "same target as canonical" family (gate-set-restriction,
symbolic-parameterization), the perturbed oracle is built by calling the
EXACT SAME canonical construction function from `build_t2_algorithms.py`
with the SAME arguments — unlike T1's perturbed build, which hand-duplicated
each construction. The independence discipline (a construction verified by
a SEPARATE, unrelated method) belongs to `validate_oracles.py`'s
alternative-construction check, not to this file; importing the canonical
builder here is not a re-use of "the same proof", just "the same target",
which is what these two families are defined to be.
"""

import json
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit, qpy
from qiskit.circuit.library import QFTGate

from bench.oracles.build_t2_algorithms import bernstein_vazirani, grover, qaoa_maxcut, qpe, simon

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
CIRCUIT_TASKS: dict[str, QuantumCircuit] = {
    # -- gate-set restriction (target unchanged from canonical) --
    "bv_4q_perturbed": bernstein_vazirani(3, 0b101),
    "grover_3q_perturbed": grover(3, [5], 2),
    "qaoa_maxcut_3q_perturbed": qaoa_maxcut(3, [(0, 1), (1, 2), (0, 2)], 0.5, 0.3),
    # -- qubit ordering / endianness (verified non-vacuous — see docstring) --
    "bv_5q_perturbed": bernstein_vazirani(4, 0b1011).reverse_bits(),
    "simon_8q_perturbed": simon(4, 0b1010).reverse_bits(),
    "qpe_4q_perturbed": qpe(3, 3).reverse_bits(),
    "grover_5q_perturbed": grover(5, [13, 20], 3).reverse_bits(),
    # -- symbolic parameterization (target unchanged from canonical) --
    "bv_6q_perturbed": bernstein_vazirani(5, 0b10110),
    "simon_10q_perturbed": simon(5, 0b10110),
    "qpe_5q_perturbed": qpe(4, 5),
    # -- relative phase (verified non-vacuous — see docstring) --
    "simon_6q_perturbed": _rz_perturb(simon(3, 0b101), 0, np.pi / 4),
    "grover_4q_perturbed": _rz_perturb(grover(4, [9], 3), 0, np.pi / 4),
    "qaoa_maxcut_4q_perturbed": _rz_perturb(
        qaoa_maxcut(4, [(0, 1), (1, 2), (2, 3), (3, 0)], 0.6, 0.4), 0, np.pi / 4
    ),
    # -- composition --
    "qpe_6q_perturbed": _compose_qft(qpe(5, 11)),
    "qaoa_maxcut_5q_perturbed": _compose_qft(
        qaoa_maxcut(5, [(0, 1), (1, 2), (2, 3), (3, 4), (4, 0)], 0.7, 0.35)
    ),
}


# -- VQE H2 (oracle_kind="energy") — JSON payloads, not .qpy. --


# theta(g1, g2, g4, g5) closed form for the ansatz X(0); RY(theta,1);
# CX(control=1,target=0) against H = g0*I + g1*Z0 + g2*Z1 + g3*Z0*Z1 +
# g4*Y0*Y1 + g5*X0*X1 — derived by hand (dE/dtheta = 0, sympy-checked) from
# the ALREADY-cited Hamiltonian (build_t2_vqe_h2.py's O'Malley et al. Table
# I source); this is calculus on a cited input, not a second unverifiable
# citation (D3e-3's concern was specifically about the empirical physics
# constants, not about deriving a formula from them). Verified to reproduce
# all three canonical `ansatz_theta_rad` values to 1e-8 before use here.
def _theta_formula(g1: float, g2: float, g4: float, g5: float) -> float:
    inner = np.sqrt((g1 - g2) ** 2 + (g4 + g5) ** 2)
    return float(-2 * np.arctan((g2 - g1 + inner) / (g4 + g5)))


def _load_canonical_vqe(task_id: str) -> dict[str, object]:
    with open(OUT_DIR / f"{task_id}.json") as f:
        payload: dict[str, object] = json.load(f)
    return payload


def _vqe_same_payload(task_id: str) -> dict[str, object]:
    """Gate-set-restriction / symbolic-parameterization: identical
    Hamiltonian, identical ansatz roles, identical theta — the perturbation
    lives entirely in the task PROMPT (restricted gates, or theta given as
    a formula instead of a decimal). For the symbolic-parameterization case
    (vqe_h2_r075_perturbed's prompt states theta via `_theta_formula`), this
    also checks the formula against the payload's own theta — the assertion
    the prompt's claimed formula corresponds to, not a one-off sandbox
    check discarded after use."""
    payload = _load_canonical_vqe(task_id)
    labels = payload["pauli_labels"]
    coeffs = payload["coeffs"]
    assert isinstance(labels, list) and isinstance(coeffs, list)
    theta_rad = payload["ansatz_theta_rad"]
    assert isinstance(theta_rad, float)
    g = dict(zip(labels, coeffs, strict=True))
    formula_theta = _theta_formula(g["IZ"], g["ZI"], g["YY"], g["XX"])
    assert np.isclose(formula_theta, theta_rad, atol=1e-8), (
        f"{task_id}: _theta_formula does not reproduce the stored ansatz_theta_rad"
    )
    return payload


def _vqe_swapped_payload(task_id: str) -> dict[str, object]:
    """Qubit-ordering: swap which physical qubit plays the X-role vs the
    RY-role (X(1); RY(theta,0); CX(control=0,target=1)), with the
    Hamiltonian's Z0/Z1 coefficients swapped to match (IZ<->ZI; ZZ/XX/YY
    are symmetric under the swap, unchanged) — an isomorphic relabeling of
    the SAME physical problem, verified below to reach the SAME
    `exact_ground_energy` with the SAME theta before being trusted."""
    payload = dict(_load_canonical_vqe(task_id))
    labels = payload["pauli_labels"]
    coeffs_raw = payload["coeffs"]
    assert isinstance(labels, list) and isinstance(coeffs_raw, list)
    coeffs = list(coeffs_raw)
    iz, zi = labels.index("IZ"), labels.index("ZI")
    coeffs[iz], coeffs[zi] = coeffs[zi], coeffs[iz]
    payload["coeffs"] = coeffs
    payload["ansatz_x_qubit"] = 1
    payload["ansatz_ry_qubit"] = 0
    payload["ansatz_cx_control"] = 0
    payload["ansatz_cx_target"] = 1
    return payload


def _verify_vqe_payload(task_id: str, payload: dict) -> None:
    from qiskit.quantum_info import SparsePauliOp, Statevector

    h = SparsePauliOp(payload["pauli_labels"], coeffs=payload["coeffs"])
    theta = payload["ansatz_theta_rad"]
    qc = QuantumCircuit(2)
    qc.x(payload.get("ansatz_x_qubit", 0))
    qc.ry(theta, payload.get("ansatz_ry_qubit", 1))
    qc.cx(payload.get("ansatz_cx_control", 1), payload.get("ansatz_cx_target", 0))
    energy = float(Statevector(qc).expectation_value(h).real)
    exact = payload["exact_ground_energy"]
    error = abs(energy - exact)
    assert error < 1e-8, f"{task_id}: perturbed payload does not reach ground energy ({error=})"


VQE_TASKS: dict[str, dict] = {
    "vqe_h2_r055_perturbed": _vqe_same_payload("vqe_h2_r055"),
    "vqe_h2_r075_perturbed": _vqe_same_payload("vqe_h2_r075"),
    "vqe_h2_r130_perturbed": _vqe_swapped_payload("vqe_h2_r130"),
}


def main() -> None:
    for task_id, circuit in CIRCUIT_TASKS.items():
        path = OUT_DIR / f"{task_id}.qpy"
        with open(path, "wb") as f:
            qpy.dump(circuit, f)
        print(f"wrote {path} ({circuit.num_qubits} qubits)")

    for task_id, payload in VQE_TASKS.items():
        _verify_vqe_payload(task_id, payload)
        path = OUT_DIR / f"{task_id}.json"
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
