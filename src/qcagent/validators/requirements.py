"""T091 — FR-009: check the planner-extracted `Requirement`s against the
generated circuit. Reference-free, like `assertions.py`, and needing no
assertion from the user at all — which is why it improves the guarantee
report in EVERY case, including the one where the user declared nothing.

No import from `qcagent.llm` (Principle I, enforced by
`tests/contract/test_architecture.py`'s scan of this package). The
requirements themselves came from an LLM upstream (planner.py), but nothing
here asks a model anything: the check is an integer comparison and a set
difference.

That provenance is exactly why a `RequirementOutcome` is not an
`AssertionOutcome` and why `GuaranteeReport.functional_correctness_verified`
lets a requirement failure VETO a correctness claim but never ESTABLISH
one. A passing `n_qubits` check means "the circuit matches what the planner
read off the description" — evidence the two agree, not evidence the
circuit is correct. A FAILING one is stronger: whatever else is true, the
circuit and the stated description disagree about something checkable.

Scope is deliberately exactly two `kind`s. `property` and `output_format`
would need natural-language → formal translation (plan.md §Verificação sem
referência explains why that stays out of scope), and `resource` has no
reference-free meaning (depth_ratio needs a reference circuit — D19). A
requirement of an unhandled `kind` produces NO outcome rather than a
passing one: emitting "passed" for a check that never ran is the exact
verification-verb borrowing this module exists to avoid.
"""

from qiskit import QuantumCircuit

from qcagent.state import Requirement, RequirementOutcome
from qcagent.validators.assertions import KNOWN_GATE_NAMES, NON_GATE_INSTRUCTIONS

CHECKABLE_KINDS = frozenset({"n_qubits", "gate_set"})


def _check_n_qubits(requirement: Requirement, circuit: QuantumCircuit) -> RequirementOutcome:
    value = requirement.value
    # `Requirement.value` is StrictInt on its integer path, so a bool never
    # reaches here through validation — it is refused at construction
    # (test_requirements.py::test_out_of_contract_values_are_refused_at_
    # the_requirement_boundary). The bool check survives only for callers
    # that bypass validation (`model_construct`, direct assignment), where
    # Python's `bool`-is-an-`int` would otherwise read True as 1 qubit.
    if not isinstance(value, int) or isinstance(value, bool):
        return RequirementOutcome(
            requirement=requirement,
            passed=None,
            detail=f"not checkable: n_qubits value is {value!r}, not an integer",
        )
    actual = circuit.num_qubits
    ok = actual == value
    return RequirementOutcome(
        requirement=requirement,
        passed=ok,
        detail=f"circuit has {actual} qubits, requirement states {value}",
    )


def _check_gate_set(requirement: Requirement, circuit: QuantumCircuit) -> RequirementOutcome:
    value = requirement.value
    if not isinstance(value, list) or not value or not all(isinstance(g, str) for g in value):
        return RequirementOutcome(
            requirement=requirement,
            passed=None,
            detail=f"not checkable: gate_set value is {value!r}, not a non-empty list of names",
        )
    allowed = {g.strip().lower() for g in value}
    unknown = sorted(g for g in allowed if g not in KNOWN_GATE_NAMES)
    if unknown:
        # NOT a failure: the planner named an instruction Qiskit doesn't
        # have, so this says nothing about the circuit. Reporting it as
        # failed would blame the generated circuit for an extraction
        # problem upstream of it.
        return RequirementOutcome(
            requirement=requirement,
            passed=None,
            detail=(
                f"not checkable: requirement names gate(s) {unknown} that are not Qiskit "
                "instruction names — cannot tell whether the circuit respects it"
            ),
        )
    # Same exclusion as GATES_SUBSET_OF, for the same reason: `measure_all()`
    # must not turn a correct H+CX circuit into a gate-set violation.
    used = {instruction.operation.name for instruction in circuit.data} - NON_GATE_INSTRUCTIONS
    extra = sorted(used - allowed)
    ok = not extra
    detail = (
        "all gates within the required set"
        if ok
        else f"circuit uses gate(s) outside the required set: {extra}"
    )
    return RequirementOutcome(requirement=requirement, passed=ok, detail=detail)


def check_requirements(
    requirements: list[Requirement], circuit: QuantumCircuit
) -> list[RequirementOutcome]:
    """One outcome per CHECKABLE requirement, in input order. Requirements
    of an unhandled `kind` are omitted entirely (see module docstring) — so
    an empty result means "nothing here was checkable", never "everything
    passed".
    """
    outcomes: list[RequirementOutcome] = []
    for requirement in requirements:
        if requirement.kind == "n_qubits":
            outcomes.append(_check_n_qubits(requirement, circuit))
        elif requirement.kind == "gate_set":
            outcomes.append(_check_gate_set(requirement, circuit))
    return outcomes
