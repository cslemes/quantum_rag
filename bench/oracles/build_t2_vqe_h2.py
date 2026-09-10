"""Builds the 3 VQE H2 oracles (T045, T049) — the missing piece flagged in
research.md D3e. `oracle_kind="energy"` needs a Hamiltonian, not a circuit,
so these serialize to JSON (`{"source", "pauli_labels", "coeffs",
"exact_ground_energy"}`), not QPY.

    uv run python -m bench.oracles.build_t2_vqe_h2

**Source, read and cited, not recalled from memory**: P. J. J. O'Malley et
al., "Scalable Quantum Simulation of Molecular Energies," Phys. Rev. X 6,
031007 (2016), arXiv:1512.06860v2, Table I. The paper's Eq. (1) gives the
2-qubit (parity-reduced, STO-3G) H2 Hamiltonian as
    H = g0*I + g1*Z0 + g2*Z1 + g3*Z0*Z1 + g4*Y0*Y1 + g5*X0*X1
and Table I tabulates (g0..g5) at 0.05-Angstrom steps of the bond length R.
The three (g0..g5) tuples below were copied by hand from `pdftotext -layout`
run directly on the arXiv PDF (not retyped from memory, not interpolated —
each is a REAL row of the actual table, verified in the extracted text to
have g4==g5 for every row, matching the paper's symmetric Y0Y1/X0X1
structure — a check the values weren't mistyped). R=0.7414 Angstrom itself
(the textbook equilibrium bond length) isn't a tabulated point (the table
steps in 0.05 increments from 0.20); R=0.75 is the closest one actually
printed, used here rather than interpolating.

`exact_ground_energy` is NOT a second citation — it's computed by exact
diagonalization of the H above (`numpy.linalg.eigh`), independently
verifiable from the cited coefficients alone, avoiding a second
unverifiable memory-recall.

**Ansatz in each task's prompt is fully specified** (exact circuit, exact
theta), same scoping choice as T2's QAOA (D3e): `check_energy` forbids free
`Parameter`s in the generated circuit (`ParameterBindingError` otherwise),
so there is no way for a generated circuit to run an actual classical
optimization loop inside the sandbox. Handing the model a fixed, numerically
pre-optimized ansatz means these tasks measure whether it can faithfully
REPRODUCE a specified parameterized circuit, not whether it can solve VQE —
same caveat as QAOA's fixed gamma/beta, and the same caution applies to
reading a high success rate here as evidence about optimization capability.
theta for each R was solved by direct scalar minimization of the exact
expectation value (scipy `minimize_scalar`, not guessed), landing at the
true ground energy to numerical precision (verified below before writing
any file) for the ansatz X(0); RY(theta, 1); CX(control=1, target=0).
"""

import json
from pathlib import Path

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import SparsePauliOp, Statevector
from scipy.optimize import minimize_scalar

OUT_DIR = Path(__file__).parent

SOURCE = (
    "O'Malley et al., 'Scalable Quantum Simulation of Molecular Energies', "
    "Phys. Rev. X 6, 031007 (2016), arXiv:1512.06860v2, Table I"
)

# task_id -> (R in Angstrom, (g0, g1, g2, g3, g4, g5))
_TABLE_ROWS: dict[str, tuple[str, tuple[float, float, float, float, float, float]]] = {
    "vqe_h2_r055": ("0.55", (0.5979, 0.4125, -0.6612, 0.6129, 0.0858, 0.0858)),
    "vqe_h2_r075": ("0.75", (0.2252, 0.3435, -0.4347, 0.5716, 0.0910, 0.0910)),
    "vqe_h2_r130": ("1.30", (-0.1629, 0.2203, -0.1238, 0.4735, 0.1083, 0.1083)),
}

# Pauli labels matching Eq. (1)'s term order — verified against Qiskit's
# label convention (rightmost character = qubit 0) before use: "IZ" is Z on
# qubit 0, "ZI" is Z on qubit 1, matching g1 (Z0) and g2 (Z1) respectively.
_PAULI_LABELS = ["II", "IZ", "ZI", "ZZ", "XX", "YY"]


def _hamiltonian(coeffs: tuple[float, ...]) -> SparsePauliOp:
    return SparsePauliOp(_PAULI_LABELS, coeffs=list(coeffs))


def _ansatz(theta: float) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.x(0)
    qc.ry(theta, 1)
    qc.cx(1, 0)
    return qc


def _solve_theta(hamiltonian: SparsePauliOp) -> tuple[float, float]:
    def energy(theta: float) -> float:
        return float(Statevector(_ansatz(theta)).expectation_value(hamiltonian).real)

    result = minimize_scalar(energy, bounds=(-1.5, 1.5), method="bounded", options={"xatol": 1e-12})
    return float(result.x), float(result.fun)


def main() -> None:
    for task_id, (r_angstrom, coeffs) in _TABLE_ROWS.items():
        hamiltonian = _hamiltonian(coeffs)
        exact_energy = float(np.linalg.eigvalsh(hamiltonian.to_matrix())[0])
        theta, ansatz_energy = _solve_theta(hamiltonian)
        error = abs(ansatz_energy - exact_energy)
        assert error < 1e-8, f"{task_id}: ansatz did not reach the ground energy (error={error})"

        payload = {
            "source": SOURCE,
            "bond_length_angstrom": r_angstrom,
            "pauli_labels": _PAULI_LABELS,
            "coeffs": list(coeffs),
            "exact_ground_energy": exact_energy,
            # recorded for reference/regeneration, not read by check_energy
            "ansatz_theta_rad": theta,
        }
        path = OUT_DIR / f"{task_id}.json"
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        print(
            f"wrote {path}  R={r_angstrom} Å  "
            f"exact_ground_energy={exact_energy:.6f} Ha  theta={theta:.6f} rad"
        )


if __name__ == "__main__":
    main()
