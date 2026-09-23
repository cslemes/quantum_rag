"""Semantic verification — layer 3 (functional correctness).

See contracts/validators.md and research.md D3, D3b.
"""

from typing import Literal

import numpy as np
from pydantic import BaseModel
from qiskit import QuantumCircuit
from qiskit.exceptions import QiskitError
from qiskit.quantum_info import (
    Operator,
    SparsePauliOp,
    Statevector,
    hellinger_fidelity,
    random_statevector,
)

from qcagent.state import ErrorRecord, SemanticResult
from qcagent.validators.circuits import (
    NotEvaluable,
    no_pure_state_reason,
    prepared_operator,
    prepared_statevector,
    unitary_part,
)
from qcagent.validators.simulator import make_simulator

EXACT_UNITARY_MAX_QUBITS = 12

# `reason` marking a verdict that could not be computed at all, because the
# generated circuit has no pure output state to compare (a NON-FINAL
# measurement or reset). Final measurements are stripped first and never
# reach this — `measure_all()` at the end of generated code is the norm, not
# an error. See validators/circuits.py for why that rule lives in one place.
NOT_EVALUABLE = "not_evaluable"


class UnitaryVerdict(BaseModel):
    equivalent: bool
    fidelity: float
    method: Literal["exact", "composition"]
    reason: str | None = None


class StateVerdict(BaseModel):
    equivalent: bool
    fidelity: float
    reason: str | None = None

    @property
    def not_evaluable(self) -> bool:
        """True when the check could not speak at all, as opposed to having
        compared the circuits and found them different. Both are
        `equivalent=False` — a verdict that cannot be produced must never
        read as a pass (Principle II) — but only this one means the
        `fidelity=0.0` beside it is a placeholder rather than a measurement,
        so nothing may report it as a similarity score."""
        return self.reason == NOT_EVALUABLE


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
    gen = prepared_operator(generated)
    if isinstance(gen, NotEvaluable):
        return UnitaryVerdict(equivalent=False, fidelity=0.0, method="exact", reason=NOT_EVALUABLE)
    op_gen, op_ref = gen, Operator(reference)
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
    # Same rule as `_check_exact`, but via the STRUCTURAL check: this path
    # exists to avoid the 4^n operator, so it must not build one just to
    # learn it cannot. The try/except below is the backstop for anything the
    # structural check doesn't name.
    unevaluable = UnitaryVerdict(
        equivalent=False, fidelity=0.0, method="composition", reason=NOT_EVALUABLE
    )
    if no_pure_state_reason(generated) is not None:
        return unevaluable

    composed = unitary_part(generated).compose(reference.inverse())
    worst = 1.0
    for seed in range(k_samples):
        psi = random_statevector(2**n_qubits, seed=seed)
        try:
            overlap = abs(psi.evolve(composed).inner(psi))
        except QiskitError:
            return unevaluable
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


def _not_evaluable_result(
    generated: QuantumCircuit, method: Literal["exact", "composition", "statevector"]
) -> SemanticResult:
    """The reference check could not be computed, so it reports nothing —
    `passed=False`, and `unitary_equiv`/`state_equiv` left None rather than
    set to False.

    False would claim a comparison was made and came out negative; None says
    no comparison happened. The distinction matters because `report.py`
    reads these to decide whether functional correctness was verified, and a
    check that never ran must not be able to look like one that ran and
    failed — nor, in the other direction, like one that passed (F10: verdict
    and actual verification diverge whenever anything but the check itself
    gets to set the verdict).

    No fidelity is reported at all here, for the same reason: there is no
    number to report, and printing 0.0000 would read as "we measured, and it
    was as wrong as possible".
    """
    return SemanticResult(
        verification_method=method,
        endianness_swapped=False,
        passed=False,
        error=ErrorRecord(
            iteration=0,
            stage="semantic",
            error_type="NonUnitaryCircuit",
            message=(
                "circuito não tem estado de saída puro para comparar com a referência "
                f"({no_pure_state_reason(generated)}) — a verificação não pôde ser "
                "executada; isto NÃO é uma divergência medida"
            ),
            payload={"not_evaluable": True},
        ),
    )


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
    if direct.reason == NOT_EVALUABLE:
        return _not_evaluable_result(generated, direct.method)
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


def check_statevector(generated: QuantumCircuit, reference: QuantumCircuit) -> StateVerdict:
    """State-preparation oracle (D3c, research.md — correction to D3/D3b):
    the task specifies only the circuit's OUTPUT STATE from |0...0>, not its
    action on every computational basis state. Unlike `check_unitary`, two
    circuits that reach the same physical state via different, unitarily
    INEQUIVALENT decompositions (e.g. GHZ via a CX chain 0->1->2 vs a CX star
    0->1,0->2 — identical state from |000>, different full unitary) must
    both verify here; `check_unitary` would wrongly reject the second.

    No size-dispatch: `Statevector(qc)` materializes 2^n amplitudes, not the
    4^n of `Operator(qc)` — cheap up to n_qubits=20 (the dataset's general
    cap, D3b/data-model.md), so there is no exact/composition split and no
    probabilistic fallback to declare, unlike the unitary oracle.

    TRAP 1 (FR-004) still applies: global phase. `Statevector.equiv()`
    already accounts for it, same guarantee `Operator.equiv()` gives
    `check_unitary`.
    """
    gen = prepared_statevector(generated)
    if isinstance(gen, NotEvaluable):
        return StateVerdict(equivalent=False, fidelity=0.0, reason=NOT_EVALUABLE)
    psi_gen, psi_ref = gen, Statevector(reference)
    if psi_gen.dim != psi_ref.dim:
        return StateVerdict(equivalent=False, fidelity=0.0, reason="dim_mismatch")
    if psi_gen.equiv(psi_ref):
        return StateVerdict(equivalent=True, fidelity=1.0)
    fid = float(abs(psi_ref.inner(psi_gen)))
    return StateVerdict(equivalent=False, fidelity=fid)


def check_statevector_with_endianness(
    generated: QuantumCircuit, reference: QuantumCircuit
) -> SemanticResult:
    """State-preparation counterpart to `check_with_endianness`. TRAP 2
    (FR-005) applies identically: a reference ported from a paper or
    PennyLane may use the opposite bit-ordering convention, and testing only
    the direct ordering would misclassify a convention mismatch as a real
    failure. Reuses the same `EndiannessSwap` category and the same
    `_structural_diff` payload shape as the unitary path — a retry gets the
    identical diagnostic regardless of which oracle kind the task uses.
    """
    direct = check_statevector(generated, reference)
    if direct.not_evaluable:
        return _not_evaluable_result(generated, "statevector")
    if direct.equivalent:
        return SemanticResult(
            state_equiv=True,
            verification_method="statevector",
            endianness_swapped=False,
            passed=True,
        )

    reversed_ref = reference.reverse_bits()
    swapped = check_statevector(generated, reversed_ref)
    if swapped.equivalent:
        return SemanticResult(
            state_equiv=False,
            verification_method="statevector",
            endianness_swapped=True,
            passed=False,
            error=ErrorRecord(
                iteration=0,
                stage="semantic",
                error_type="EndiannessSwap",
                message=(
                    "estado casa com a referência apenas quando os bits "
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
        state_equiv=False,
        verification_method="statevector",
        endianness_swapped=False,
        passed=False,
        error=ErrorRecord(
            iteration=0,
            stage="semantic",
            error_type="WrongGateDecomposition",
            message=(f"estado gerado diverge da referência (fidelidade={direct.fidelity:.4f})"),
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
