"""Semantic verification — layer 3 (functional correctness).

See contracts/validators.md and research.md D3, D3b.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit
from qiskit.quantum_info import (
    Operator,
    SparsePauliOp,
    Statevector,
    hellinger_fidelity,
    random_statevector,
)

from qcagent.state import ErrorRecord, SemanticResult
from qcagent.validators.simulator import make_simulator

EXACT_UNITARY_MAX_QUBITS = 12


class UnitaryVerdict(BaseModel):
    equivalent: bool
    fidelity: float
    method: Literal["exact", "composition"]
    reason: str | None = None


class DistributionVerdict(BaseModel):
    hellinger_fidelity: float  # mean across seeds
    hellinger_std: float  # deviation across seeds — mean alone hides instability
    tvd: float  # mean across seeds


class EnergyVerdict(BaseModel):
    energy_error: float
    passed: bool


class MissingMeasurementError(Exception):
    """Raised by `check_distribution` when `generated` has no measurement
    instructions. Without this check, Aer's own failure ("No counts for
    experiment") only surfaces after a full simulation run and doesn't say
    why. Maps to the closed taxonomy's `MissingMeasurement`
    (data-model.md) — the caller classifies it once it has iteration
    context to build an `ErrorRecord`.
    """


class ParameterBindingError(Exception):
    """Raised by `check_energy` when `generated` has unbound `Parameter`s.
    Qiskit's own failure here is a bare `TypeError` ("cannot be cast to a
    float") that doesn't say why. Maps to the closed taxonomy's
    `ParameterBindingError` (data-model.md).
    """


def _check_exact(generated: QuantumCircuit, reference: QuantumCircuit) -> UnitaryVerdict:
    """TRAP 1 — global phase. Two correct implementations of the same
    circuit routinely differ by e^{iθ}. `Operator.equiv()` already accounts
    for this; comparing the matrices directly would mark them wrong. NEVER
    use `np.allclose` on the matrices themselves (FR-004).

    When `equiv()` is false, compute a continuous fidelity instead of just
    reporting failure:
        |Tr(U_ref† @ U_gen)| / dim
    """
    op_gen, op_ref = Operator(generated), Operator(reference)
    if op_gen.dim != op_ref.dim:
        return UnitaryVerdict(equivalent=False, fidelity=0.0, method="exact", reason="dim_mismatch")
    if op_gen.equiv(op_ref):
        return UnitaryVerdict(equivalent=True, fidelity=1.0, method="exact")
    fid = abs(np.trace(op_ref.adjoint().data @ op_gen.data)) / op_gen.dim[0]
    return UnitaryVerdict(equivalent=False, fidelity=float(fid), method="exact")


def _check_by_composition(
    generated: QuantumCircuit,
    reference: QuantumCircuit,
    n_qubits: int,
    k_samples: int = 5,
    atol: float = 1e-9,
) -> UnitaryVerdict:
    """Cost 2^n instead of 4^n. If generated ∘ reference⁻¹ ≡ I, every state
    returns unchanged up to global phase.

    The `abs()` of the inner product gives global-phase tolerance for free
    — the same guarantee as FR-004, without ever materializing a matrix.

    Probabilistic: with 5 Haar-random states the false-positive chance is
    negligible, but NOT zero. This must be stated in the dissertation.
    """
    composed = generated.compose(reference.inverse())
    worst = 1.0
    for seed in range(k_samples):
        psi = random_statevector(2**n_qubits, seed=seed)
        overlap = abs(psi.evolve(composed).inner(psi))
        worst = min(worst, overlap)
        if not np.isclose(overlap, 1.0, atol=atol):
            return UnitaryVerdict(equivalent=False, fidelity=float(worst), method="composition")
    return UnitaryVerdict(equivalent=True, fidelity=1.0, method="composition")


def check_unitary(
    generated: QuantumCircuit, reference: QuantumCircuit, n_qubits: int, k_samples: int = 5
) -> UnitaryVerdict:
    """Dispatches by size — see D3b:

      n_qubits <= 12  -> _check_exact()         (Operator.equiv, 4^n)
      n_qubits >  12  -> _check_by_composition() (statevector, 2^n)

    The method used IS RECORDED in SemanticResult.verification_method
    (by `check_with_endianness`), so analysis can segment results by
    verification method.
    """
    if n_qubits <= EXACT_UNITARY_MAX_QUBITS:
        return _check_exact(generated, reference)
    return _check_by_composition(generated, reference, n_qubits, k_samples=k_samples)


def _gate_sequence(circuit: QuantumCircuit) -> list[list]:
    """Ordered [gate_name, [qubit_indices]] for every instruction in the
    circuit, straight from the already-deserialized QPY circuit's `.data`
    (no new simulation).

    CAUTION (research.md D14): kept in `_structural_diff`'s payload as raw
    data, but do NOT compare `expected_gate_sequence[i]` against
    `actual_gate_sequence[i]` position-by-position and render it as a
    prescription ("expected X here"). `.data` order is not canonical —
    equivalent circuits can order/route their gates differently (e.g. GHZ
    prep via a CX chain 0->1->2 vs a CX star 0->1,0->2: both entangle
    correctly from |0..0>, same gate multiset, different `.data` order).
    A positional diff can't distinguish that from an actual bug, and in a
    real run it did exactly the wrong thing: flagged the valid topology
    choice as the error and said nothing about the genuine bug (extra H
    gates) elsewhere in the same circuit. `nodes/generator.py`'s
    `render_structural_diff` intentionally does not render this field for
    that reason — it's here for future analysis (e.g. an
    order-invariant/edit-distance diff, or T064's qualitative coding), not
    for feeding the retry loop as-is.
    """
    return [
        [instr.operation.name, [circuit.find_bit(q).index for q in instr.qubits]]
        for instr in circuit.data
    ]


def _structural_diff(generated: QuantumCircuit, reference: QuantumCircuit) -> dict:
    """Qubit-count and gate-count-by-type diff between the generated circuit
    and the reference, plus the raw per-gate qubit-target sequence of each
    (see `_gate_sequence`'s caution on that last part) — every field here is
    a static property already sat on the two `QuantumCircuit` objects
    (`.num_qubits`, `.count_ops()`, `.data`), not a new simulation pass.
    Attached to a semantic ErrorRecord's `payload` so a retry has something
    more actionable than a bare fidelity scalar: a fidelity number says
    "wrong" but not "wrong how".
    """
    return {
        "expected_n_qubits": reference.num_qubits,
        "actual_n_qubits": generated.num_qubits,
        "expected_gate_counts": dict(reference.count_ops()),
        "actual_gate_counts": dict(generated.count_ops()),
        "expected_gate_sequence": _gate_sequence(reference),
        "actual_gate_sequence": _gate_sequence(generated),
    }


def check_with_endianness(
    generated: QuantumCircuit, reference: QuantumCircuit, n_qubits: int
) -> SemanticResult:
    """TRAP 2 — bit-ordering convention (FR-005).

    Qiskit is little-endian. References ported from papers or PennyLane
    frequently use the opposite convention. Verify against the original
    reference AND against `reference.reverse_bits()`.

    If only the reversed one matches -> endianness_swapped=True,
    passed=False, error_type="EndiannessSwap". This is its OWN category,
    not a generic failure: treating it as one would artificially inflate
    the error rate and erase an interesting finding from the taxonomy.
    """
    direct = check_unitary(generated, reference, n_qubits)
    if direct.equivalent:
        return SemanticResult(
            unitary_equiv=True,
            verification_method=direct.method,
            endianness_swapped=False,
            passed=True,
        )

    reversed_ref = reference.reverse_bits()
    swapped = check_unitary(generated, reversed_ref, n_qubits)
    if swapped.equivalent:
        return SemanticResult(
            unitary_equiv=False,
            verification_method=swapped.method,
            endianness_swapped=True,
            passed=False,
            error=ErrorRecord(
                iteration=0,
                stage="semantic",
                error_type="EndiannessSwap",
                message=(
                    "circuito casa com a referência apenas quando os bits "
                    "são invertidos — divergência de convenção, não erro "
                    "funcional"
                ),
                payload={
                    **_structural_diff(generated, reference),
                    "reversed_bit_order_matches": True,
                    "direct_fidelity": direct.fidelity,
                },
            ),
        )

    return SemanticResult(
        unitary_equiv=False,
        verification_method=direct.method,
        endianness_swapped=False,
        passed=False,
        error=ErrorRecord(
            iteration=0,
            stage="semantic",
            error_type="WrongGateDecomposition",
            message=(
                f"unitária diverge da referência (fidelidade={direct.fidelity:.4f}, "
                f"método={direct.method})"
            ),
            payload={
                **_structural_diff(generated, reference),
                "reversed_bit_order_matches": False,
                "direct_fidelity": direct.fidelity,
                "reversed_bit_order_fidelity": swapped.fidelity,
            },
        ),
    )


def _total_variation_distance(counts_a: dict[str, int], counts_b: dict[str, int]) -> float:
    total_a = sum(counts_a.values())
    total_b = sum(counts_b.values())
    keys = set(counts_a) | set(counts_b)
    return 0.5 * sum(abs(counts_a.get(k, 0) / total_a - counts_b.get(k, 0) / total_b) for k in keys)


def check_distribution(
    generated: QuantumCircuit,
    reference_counts: dict[str, int],
    shots: int = 8192,
    seeds: tuple[int, ...] = (1, 2, 3),
) -> DistributionVerdict:
    """Hellinger fidelity (primary) and TVD (secondary), mean and deviation
    across the seeds. The deviation goes in the report — the mean alone
    hides instability.
    """
    if "measure" not in generated.count_ops():
        raise MissingMeasurementError(
            "generated circuit has no measurement instructions — cannot "
            "compare against a counts-based reference"
        )

    n_qubits = generated.num_qubits
    fidelities: list[float] = []
    tvds: list[float] = []
    for seed in seeds:
        sim = make_simulator(n_qubits, seed=seed)
        result = sim.run(generated, shots=shots).result()
        counts = result.get_counts()
        fidelities.append(hellinger_fidelity(counts, reference_counts))
        tvds.append(_total_variation_distance(counts, reference_counts))

    return DistributionVerdict(
        hellinger_fidelity=float(np.mean(fidelities)),
        hellinger_std=float(np.std(fidelities)),
        tvd=float(np.mean(tvds)),
    )


def check_energy(
    generated: QuantumCircuit,
    hamiltonian: SparsePauliOp,
    exact_value: float,
    tol: float = 1e-2,
) -> EnergyVerdict:
    """For VQE: absolute error against exact diagonalization."""
    if generated.parameters:
        raise ParameterBindingError(
            "generated circuit has unbound parameters: "
            f"{sorted(p.name for p in generated.parameters)} — cannot "
            "evaluate expectation value"
        )
    state = Statevector(generated)
    computed = state.expectation_value(hamiltonian).real
    error = abs(computed - exact_value)
    return EnergyVerdict(energy_error=float(error), passed=error <= tol)
