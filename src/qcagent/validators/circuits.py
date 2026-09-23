"""Circuit primitives shared by every check that needs a pure output state.

This module exists because the same defect was fixed twice and missed once.
`Statevector(qc)` and `Operator(qc)` raise `QiskitError` on any circuit
carrying a measurement, and real generated code calls `measure_all()`
constantly. The assertion evaluator hit that end to end (T092) and grew its
own private fix; the reference oracles in `semantic.py` had the identical
bug and kept it, because no test drove a measured circuit into them — until
the first live suite run, where one task's `measure_all()` took down the
whole 360-run suite mid-flight.

So the primitive lives here, once, and both callers use it. The two rules it
encodes are the same in both paths and must stay that way:

* **Final measurements are stripped.** A measurement at the end samples the
  prepared state, it doesn't change it, so it must not change the verdict.
* **A non-final measurement or reset is NOT EVALUABLE.** There is no pure
  output state to compare against, so the answer is neither "equivalent" nor
  "different" — it is "this check cannot speak". Never a crash, and above
  all never a silent pass (Principle II).
"""

from qiskit import QuantumCircuit
from qiskit.exceptions import QiskitError
from qiskit.quantum_info import Operator, Statevector


class NotEvaluable:
    """Sentinel returned by an evaluator when the question asked is
    well-formed but not well-posed for the circuit it was asked about.

    Carries `reason` so callers can report exactly why rather than a bare
    "N/A" — a verdict a user can't interpret is barely better than no
    verdict at all.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"NotEvaluable({self.reason!r})"


def unitary_part(circuit: QuantumCircuit) -> QuantumCircuit:
    """The circuit with its FINAL measurements removed — what it prepares,
    without how it is sampled. Non-final measurements survive here on
    purpose, so that the constructors below fail on them and the caller gets
    `NotEvaluable` instead of a quietly truncated circuit."""
    return circuit.remove_final_measurements(inplace=False)


# Instructions that destroy the pure output state when they appear anywhere
# but the very end. `barrier` is deliberately absent: it is a compiler
# directive, carries no physics, and evolves fine. This list is the CHEAP
# pre-check for callers (like the 2^n composition path) that must not pay to
# materialize an operator just to discover they cannot; the `QiskitError`
# handlers below remain the backstop, so an instruction missing from here
# still yields `NotEvaluable` rather than a crash.
NON_UNITARY_INSTRUCTIONS = frozenset({"measure", "reset", "initialize", "store"})


def no_pure_state_reason(circuit: QuantumCircuit) -> str | None:
    """Cheap structural check — the reason `circuit` has no pure output
    state, or None if it looks evaluable. Costs one pass over the
    instruction list, no simulation."""
    # Unbound parameters first: a parametrized ansatz describes a FAMILY of
    # states, not one state, so there is nothing to compare against a
    # reference. Qiskit signals this with a bare `TypeError` out of float
    # conversion, NOT a QiskitError — which is exactly how it escaped the
    # handlers below and crashed 15 runs of the first live suite (bug 19).
    # `semantic.py` already documented that TypeError for `check_energy` and
    # never applied it here.
    if circuit.parameters:
        names = ", ".join(sorted(str(p) for p in circuit.parameters))
        return (
            f"circuit has unbound parameters ({names}) — it describes a family of states, not one"
        )
    offenders = sorted(
        {
            instruction.operation.name
            for instruction in unitary_part(circuit).data
            if instruction.operation.name in NON_UNITARY_INSTRUCTIONS
        }
    )
    if not offenders:
        return None
    return (
        "circuit has no pure output state: it contains non-final "
        f"{', '.join(offenders)} instruction(s)"
    )


def prepared_statevector(circuit: QuantumCircuit) -> Statevector | NotEvaluable:
    """The state `circuit` prepares from |0...0>, or why it has none."""
    try:
        return Statevector.from_instruction(unitary_part(circuit))
    except (QiskitError, TypeError) as exc:
        return NotEvaluable(_no_pure_state(exc))


def prepared_operator(circuit: QuantumCircuit) -> Operator | NotEvaluable:
    """The unitary `circuit` implements, or why it implements none."""
    try:
        return Operator(unitary_part(circuit))
    except (QiskitError, TypeError) as exc:
        return NotEvaluable(_no_pure_state(exc))


def _no_pure_state(exc: Exception) -> str:
    """Why an evaluation failed, from the exception the constructor raised.

    Catching `TypeError` alongside `QiskitError` is not defensive padding.
    An `except` clause is an invisible CONTRACT about how the code beneath
    it fails, and `except QiskitError` reads as exhaustive because the
    library is Qiskit — it is not, because Qiskit lets arithmetic errors
    from unbound `ParameterExpression`s escape as plain `TypeError`. That
    gap cost 15 runs before it was found (bug 19); no code review noticed
    it, and no test with textbook input reached it.
    """
    return (
        "circuit has no pure output state (a non-final measurement, reset or other "
        f"non-unitary instruction): {exc}"
    )
