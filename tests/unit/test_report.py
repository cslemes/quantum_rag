"""Tests for report.py (US4, T093-T094). T095 is the MANDATORY test
(Principle II) — `test_no_correctness_claim_without_verified_assertion` and
`test_cannot_construct_a_lying_report` below. See plan.md §Relatório de
garantia: SC-004 must be structurally impossible to violate, not merely
untested.
"""

import pytest
from pydantic import ValidationError
from qiskit import QuantumCircuit

from qcagent.report import GuaranteeReport, render_guarantee_report
from qcagent.state import (
    ErrorRecord,
    Requirement,
    RequirementOutcome,
    ResourceResult,
    SemanticResult,
)
from qcagent.validators.assertions import evaluate_assertions, parse_assertions


def _report(**overrides) -> GuaranteeReport:
    defaults = dict(
        executed=True,
        transpiled=True,
        requirements=[],
        assertions=[],
        n_qubits_correction=None,
        reference=None,
        coupling_map_name=None,
        topology_respected=None,
        resource=None,
        hardware_note=None,
    )
    defaults.update(overrides)
    return GuaranteeReport(**defaults)


def _requirement_outcome(kind: str, passed: bool | None, value=None) -> RequirementOutcome:
    return RequirementOutcome(
        requirement=Requirement(id="r1", kind=kind, description="d", value=value),
        passed=passed,
        detail="detail text",
    )


def _bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


# ---------------------------------------------------------------------------
# T095 — MANDATORY (Principle II)
# ---------------------------------------------------------------------------


def test_no_correctness_claim_without_verified_assertion() -> None:
    """For assertions=[] and for assertions only with passed=False: (a)
    functional_correctness_verified is False; (b) the rendered text
    CONTAINS the explicit non-verification statement; (c) it does NOT
    contain an unqualified correctness claim."""
    empty = _report(assertions=[])
    assert empty.functional_correctness_verified is False
    text_empty = render_guarantee_report(empty)
    assert "NOT VERIFIED" in text_empty
    assert "FUNCTIONAL CORRECTNESS: VERIFIED —" not in text_empty

    assertions = parse_assertions('MEASURES == "00"', 2)
    only_failing = evaluate_assertions(assertions, _bell())
    assert all(o.passed is False for o in only_failing)
    report = _report(assertions=only_failing)
    assert report.functional_correctness_verified is False
    text = render_guarantee_report(report)
    assert "NOT VERIFIED" in text
    assert "FUNCTIONAL CORRECTNESS: VERIFIED —" not in text


def test_cannot_construct_a_lying_report() -> None:
    """Adversarial half of T095: `functional_correctness_verified` is a
    `@computed_field`, and `extra="forbid"` rejects any attempt to pass it
    (or anything else it doesn't declare) to the constructor directly —
    this must be structurally impossible, not just untested.

    Asserts the SPECIFIC error, not just that some ValidationError occurred:
    when `reference` became a required field, this test kept passing
    without it — raising for the missing field, not the forbidden one — and
    would have gone on passing with `extra="forbid"` deleted."""
    with pytest.raises(ValidationError) as excinfo:
        GuaranteeReport(
            executed=True,
            transpiled=True,
            requirements=[],
            assertions=[],
            n_qubits_correction=None,
            reference=None,
            coupling_map_name=None,
            topology_respected=None,
            resource=None,
            hardware_note=None,
            functional_correctness_verified=True,
        )
    errors = excinfo.value.errors()
    assert [(e["type"], e["loc"]) for e in errors] == [
        ("extra_forbidden", ("functional_correctness_verified",))
    ]


# ---------------------------------------------------------------------------
# functional_correctness_verified
# ---------------------------------------------------------------------------


def test_verified_true_when_all_assertions_pass() -> None:
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    outcomes = evaluate_assertions(assertions, _bell())
    report = _report(assertions=outcomes)
    assert report.functional_correctness_verified is True


def test_not_evaluable_never_counts_as_passing() -> None:
    only_00 = QuantumCircuit(2)
    assertions = parse_assertions("PHASE_DIFF(|00>,|11>) ~= 0", 2)
    outcomes = evaluate_assertions(assertions, only_00)
    assert outcomes[0].passed is None
    report = _report(assertions=outcomes)
    assert report.functional_correctness_verified is False


def test_one_failure_among_passes_is_not_verified() -> None:
    text = 'PROBABILITY(|11>) ~= 0.5\nMEASURES == "00"'
    assertions = parse_assertions(text, 2)
    outcomes = evaluate_assertions(assertions, _bell())
    report = _report(assertions=outcomes)
    assert report.functional_correctness_verified is False


# ---------------------------------------------------------------------------
# only_trivial_input_tested
# ---------------------------------------------------------------------------


def test_only_trivial_input_tested_true_when_no_assertion_uses_input() -> None:
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    outcomes = evaluate_assertions(assertions, _bell())
    assert _report(assertions=outcomes).only_trivial_input_tested is True


def test_only_trivial_input_tested_false_when_an_assertion_uses_input() -> None:
    assertions = parse_assertions("INPUT(|01>) THEN PROBABILITY(|01>) ~= 1.0", 2)
    outcomes = evaluate_assertions(assertions, QuantumCircuit(2))
    assert _report(assertions=outcomes).only_trivial_input_tested is False


def test_only_trivial_input_tested_false_when_no_assertions() -> None:
    assert _report(assertions=[]).only_trivial_input_tested is False


def test_gate_restriction_alone_does_not_trigger_input_coverage_note() -> None:
    """GATES_SUBSET_OF is structural, has no input_state field at all —
    must not count toward "input-capable" on either side."""
    assertions = parse_assertions('GATES_SUBSET_OF({"h", "cx"})', 2)
    outcomes = evaluate_assertions(assertions, _bell())
    report = _report(assertions=outcomes)
    assert report.only_trivial_input_tested is False
    assert "Input coverage" not in render_guarantee_report(report)


# ---------------------------------------------------------------------------
# Rendering — topology/resource
# ---------------------------------------------------------------------------


def test_no_coupling_map_omits_topology_section() -> None:
    text = render_guarantee_report(_report())
    assert "Topology" not in text
    assert "Resource" not in text


def test_coupling_map_without_reference_states_resource_has_no_meaning() -> None:
    text = render_guarantee_report(_report(coupling_map_name="linear_5", topology_respected=True))
    assert "Topology: respects the declared coupling map (linear_5)" in text
    assert "no meaning without one" in text


def test_coupling_map_not_respected_says_so() -> None:
    text = render_guarantee_report(_report(coupling_map_name="linear_5", topology_respected=False))
    assert "does NOT respect" in text


def test_resource_present_renders_ratios() -> None:
    resource = ResourceResult(
        depth=4, cx_count=3, width=2, depth_ratio=1.5, cx_ratio=1.0, passed=True
    )
    text = render_guarantee_report(
        _report(coupling_map_name="linear_5", topology_respected=True, resource=resource)
    )
    assert "depth_ratio=1.50" in text
    assert "cx_ratio=1.00" in text
    assert "within the configured limit" in text


def test_hardware_note_rendered() -> None:
    text = render_guarantee_report(_report(hardware_note="measured on ibm_kyiv, 1024 shots"))
    assert "Hardware: measured on ibm_kyiv, 1024 shots" in text


# ---------------------------------------------------------------------------
# _render_assertion — one per Assertion kind, plus INPUT prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "n_qubits", "expected_substring"),
    [
        ("PROBABILITY(|11>) ~= 0.5", 2, "PROBABILITY(|11>) ~= 0.5"),
        ("AMPLITUDE(|00>) == AMPLITUDE(|11>)", 2, "AMPLITUDE(|00>) == AMPLITUDE(|11>)"),
        ("PHASE_DIFF(|00>,|11>) ~= 0", 2, "PHASE_DIFF(|00>,|11>) ~= 0"),
        ('MEASURES == "01"', 2, 'MEASURES == "01"'),
        ('MEASURES([1,0]) == "01"', 2, 'MEASURES([1, 0]) == "01"'),
        ('EIGENSTATE_OF("ZI", -1)', 2, 'EIGENSTATE_OF("ZI", -1)'),
        ('QUBIT(0) == "|+>"', 2, 'EIGENSTATE_OF("IX", +1)'),
        ('GATES_SUBSET_OF({"h", "cx"})', 2, 'GATES_SUBSET_OF({"cx", "h"})'),
        ('INPUT(|01>) THEN MEASURES == "01"', 2, "INPUT(|01>) THEN MEASURES"),
    ],
)
def test_render_assertion_forms(text: str, n_qubits: int, expected_substring: str) -> None:
    assertions = parse_assertions(text, n_qubits)
    outcomes = evaluate_assertions(assertions, QuantumCircuit(n_qubits))
    rendered = render_guarantee_report(_report(assertions=outcomes))
    assert expected_substring in rendered


# ---------------------------------------------------------------------------
# T091 — requirements: veto semantics and honest "none checked" wording
# ---------------------------------------------------------------------------


def test_failed_requirement_vetoes_a_correctness_claim() -> None:
    """A requirement failure must block the claim even when every declared
    assertion passed — the circuit and the description disagree about
    something directly checkable, and no correctness claim survives that."""
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    outcomes = evaluate_assertions(assertions, _bell())
    assert _report(assertions=outcomes).functional_correctness_verified is True

    vetoed = _report(assertions=outcomes, requirements=[_requirement_outcome("n_qubits", False, 3)])
    assert vetoed.functional_correctness_verified is False
    text = render_guarantee_report(vetoed)
    assert "NOT VERIFIED" in text
    assert "directly checkable" in text


def test_passing_requirements_alone_never_establish_a_correctness_claim() -> None:
    """The asymmetry that keeps LLM-extracted requirements from being
    treated as verification: passing ones are not evidence of correctness."""
    report = _report(requirements=[_requirement_outcome("n_qubits", True, 2)], assertions=[])
    assert report.functional_correctness_verified is False
    assert "NOT VERIFIED" in render_guarantee_report(report)


def test_not_checkable_requirement_vetoes_nothing() -> None:
    assertions = parse_assertions("PROBABILITY(|11>) ~= 0.5", 2)
    outcomes = evaluate_assertions(assertions, _bell())
    report = _report(
        assertions=outcomes, requirements=[_requirement_outcome("gate_set", None, ["hadamard"])]
    )
    assert report.functional_correctness_verified is True


def test_empty_requirements_does_not_claim_a_check_happened() -> None:
    """ "Requirements checked: none" read as "we checked and found none".
    The word "checked" is a verification verb and must not be borrowed for
    a check that never ran."""
    text = render_guarantee_report(_report())
    assert "Requirements checked: none" not in text
    assert "none checked" in text
    assert "no qubit-count or gate-set requirement was extracted" in text


def test_requirements_enumerated_individually_when_present() -> None:
    report = _report(
        requirements=[
            _requirement_outcome("n_qubits", True, 2),
            _requirement_outcome("gate_set", False, ["h"]),
        ]
    )
    text = render_guarantee_report(report)
    assert "Requirements (1/2 passed):" in text
    assert "[PASS] n_qubits" in text
    assert "[FAIL] gate_set" in text


# ---------------------------------------------------------------------------
# Verdict-first ordering
# ---------------------------------------------------------------------------


def test_verdict_precedes_every_affirmative_fact() -> None:
    """Three "yes"-shaped lines ahead of the verdict is the shape that
    produces optimistic skimming — the verdict must come first."""
    report = _report(coupling_map_name="linear_5", topology_respected=True)
    text = render_guarantee_report(report)
    verdict_at = text.index("FUNCTIONAL CORRECTNESS:")
    for affirmative in ("Executed: yes", "Transpiled: yes"):
        assert text.index(affirmative) > verdict_at, f"{affirmative!r} precedes the verdict"


def test_verdict_appears_exactly_once() -> None:
    """Leading with it must not also leave a copy at the end — a repeated
    verdict reads as padding and invites skipping both."""
    text = render_guarantee_report(_report())
    assert text.count("FUNCTIONAL CORRECTNESS:") == 1


# ---------------------------------------------------------------------------
# Found end to end (T092/T098): stale verdicts, the reference path
# ---------------------------------------------------------------------------


def _passing_outcomes():
    return evaluate_assertions(parse_assertions("PROBABILITY(|11>) ~= 0.5", 2), _bell())


@pytest.mark.parametrize(("executed", "transpiled"), [(False, False), (True, False)])
def test_never_verified_about_a_circuit_that_did_not_run(executed: bool, transpiled: bool) -> None:
    """Structural guard: nothing can have been checked on code that didn't
    execute or transpile, so any outcome present is stale. End to end, stale
    verdicts once produced VERIFIED next to status=failed_static."""
    report = _report(executed=executed, transpiled=transpiled, assertions=_passing_outcomes())
    assert report.functional_correctness_verified is False
    text = render_guarantee_report(report)
    assert "FUNCTIONAL CORRECTNESS: NOT VERIFIED — the final circuit did not" in text
    assert "executing successfully" not in text


_EXACT = SemanticResult(passed=True, verification_method="exact", unitary_equiv=True)


@pytest.mark.parametrize(
    ("reference", "must_say"),
    [
        (_EXACT, "exact check"),
        (
            SemanticResult(passed=True, verification_method="composition", unitary_equiv=True),
            "probabilistic check, not an exact one",
        ),
        (
            SemanticResult(passed=True, verification_method="statevector", state_equiv=True),
            "from |0...0> only",
        ),
        (SemanticResult(passed=True, hellinger_fidelity=0.9951), "Hellinger fidelity 0.9951"),
        (SemanticResult(passed=True, energy_error=0.0012), "energy check"),
    ],
)
def test_a_passed_reference_verifies_and_says_what_it_actually_proved(
    reference: SemanticResult, must_say: str
) -> None:
    """The methods do not prove the same thing. A single "matches the
    reference" would over-claim for everything but the exact check."""
    report = _report(reference=reference)
    assert report.functional_correctness_verified is True
    text = render_guarantee_report(report)
    verdict = text.splitlines()[2]
    assert verdict.startswith("FUNCTIONAL CORRECTNESS: VERIFIED")
    assert must_say in verdict
    assert "nothing about its behavior was checked" not in text
    assert "Reference comparison: PASSED" in text


def test_failed_reference_with_every_assertion_passing_names_the_reference() -> None:
    """A reachable state (semantic fails after assertions pass, loop aborts)
    whose verdict branch once rendered "NOT VERIFIED —  of 1 declared
    assertions" with an empty reason."""
    failed = SemanticResult(
        passed=False,
        verification_method="exact",
        unitary_equiv=False,
        error=ErrorRecord(
            iteration=1,
            stage="semantic",
            error_type="WrongGateDecomposition",
            message="unitary differs",
        ),
    )
    report = _report(reference=failed, assertions=_passing_outcomes())
    assert report.functional_correctness_verified is False
    verdict = render_guarantee_report(report).splitlines()[2]
    assert "does not match the verified reference (unitary differs)" in verdict
    assert " of 1 declared" not in verdict


def test_a_failed_user_assertion_vetoes_even_a_reference_match() -> None:
    violated = evaluate_assertions(parse_assertions('MEASURES == "00"', 2), _bell())
    report = _report(reference=_EXACT, assertions=violated)
    assert report.functional_correctness_verified is False


def test_resource_result_is_shown_even_without_a_coupling_map() -> None:
    """Was nested under the topology branch, so a resource cutoff with no
    coupling map never appeared in the report."""
    resource = ResourceResult(
        depth=6, cx_count=5, width=2, depth_ratio=3.0, cx_ratio=5.0, passed=False
    )
    text = render_guarantee_report(_report(reference=_EXACT, resource=resource))
    assert "EXCEEDS the configured limit" in text
    assert "Topology" not in text
