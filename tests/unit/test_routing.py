"""Tests for nodes/routing.py's conditional edges — focused on the US3
additions (T088): `route_after_assertion_check`, the updated
`route_after_static` target, and `terminal_status`'s new
`assertion_not_evaluable` branch. Also T096's `finalize`/
`_build_guarantee_report`. See plan.md's ASCII diagram.
"""

from qcagent.nodes.routing import (
    finalize,
    route_after_assertion_check,
    route_after_static,
    terminal_status,
)
from qcagent.report import GuaranteeReport
from qcagent.state import (
    AssertionOutcome,
    CriticDecision,
    ErrorRecord,
    MeasuresAssertion,
    Requirement,
    RequirementOutcome,
    ResourceResult,
    SemanticResult,
    StaticResult,
)


def _measures(expected: str) -> MeasuresAssertion:
    return MeasuresAssertion(qubits=None, expected=expected)


def _outcome(passed: bool | None) -> AssertionOutcome:
    return AssertionOutcome(assertion=_measures("00"), passed=passed, detail="")


def test_route_after_static_goes_to_assertion_check_when_transpiled() -> None:
    static = StaticResult(parsed=True, executed=True, transpiled=True)
    assert route_after_static({"static": static}) == "assertion_check"


def test_route_after_static_goes_to_critic_when_not_transpiled() -> None:
    static = StaticResult(parsed=True, executed=False, transpiled=False)
    assert route_after_static({"static": static}) == "critic"


def test_route_after_assertion_check_violation_goes_to_critic() -> None:
    state = {"assertion_results": [_outcome(False)], "oracle_ref": "bell"}
    assert route_after_assertion_check(state) == "critic"


def test_route_after_assertion_check_not_evaluable_goes_to_critic() -> None:
    state = {"assertion_results": [_outcome(None)], "oracle_ref": "bell"}
    assert route_after_assertion_check(state) == "critic"


def test_route_after_assertion_check_passed_with_oracle_ref_goes_to_semantic() -> None:
    state = {"assertion_results": [_outcome(True)], "oracle_ref": "bell"}
    assert route_after_assertion_check(state) == "semantic_check"


def test_route_after_assertion_check_passed_without_oracle_ref_goes_to_critic() -> None:
    """The product path (US3/US4): no reference circuit exists, so there is
    nothing left to check after assertions pass — straight to critic (which
    will route "done" since there is no pending error), never
    resource_check (which requires oracle_ref unconditionally, regardless
    of whether a coupling_map was declared — see routing.py's docstring)."""
    state = {"assertion_results": [_outcome(True)], "oracle_ref": None}
    assert route_after_assertion_check(state) == "critic"


def test_route_after_assertion_check_empty_list_with_no_oracle_ref_goes_to_critic() -> None:
    state: dict[str, object] = {"assertion_results": [], "oracle_ref": None}
    assert route_after_assertion_check(state) == "critic"


def test_route_after_assertion_check_missing_key_treated_as_empty() -> None:
    assert route_after_assertion_check({"oracle_ref": None}) == "critic"


# ---------------------------------------------------------------------------
# terminal_status — assertion_not_evaluable and completed_unverified
# ---------------------------------------------------------------------------


def _empty_report(**overrides) -> GuaranteeReport:
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


def test_terminal_status_assertion_not_evaluable() -> None:
    state = {
        "decision": CriticDecision(action="abort", rationale="r"),
        "error_history": [
            ErrorRecord(
                iteration=1, stage="semantic", error_type="AssertionNotEvaluable", message="m"
            )
        ],
    }
    assert terminal_status(state, _empty_report()) == "assertion_not_evaluable"


def test_terminal_status_assertion_violated_is_ordinary_failed_semantic() -> None:
    """AssertionViolated shares stage="semantic" with AssertionNotEvaluable
    but must NOT get the special status — only a resolved-to-"wrong"
    assertion, not one that never resolved either way."""
    state = {
        "decision": CriticDecision(action="abort", rationale="r"),
        "error_history": [
            ErrorRecord(iteration=1, stage="semantic", error_type="AssertionViolated", message="m")
        ],
    }
    assert terminal_status(state, _empty_report()) == "failed_semantic"


def test_clean_run_that_verified_nothing_is_completed_unverified_not_success() -> None:
    """The whole point of the split: `status` alone must not read as
    approval for a run where nothing about functional correctness was
    checked. An aggregator that only looks at `status` gets the truth."""
    state = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
        "semantic": None,
    }
    assert terminal_status(state, _empty_report()) == "completed_unverified"


def test_passing_assertions_earn_success_without_any_oracle() -> None:
    outcome = AssertionOutcome(
        assertion=MeasuresAssertion(qubits=None, expected="00"), passed=True, detail="ok"
    )
    state = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
        "semantic": None,
    }
    report = _empty_report(assertions=[outcome])
    assert report.functional_correctness_verified is True
    assert terminal_status(state, report) == "success"


def test_semantic_pass_earns_success_keeping_the_suite_metric_unchanged() -> None:
    """The regression-suite path: `oracle_ref` is always present, so a
    reference comparison passing still means `success` — this split must
    not move the suite's own numbers."""
    state = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
    }
    assert (
        terminal_status(
            state,
            _empty_report(
                reference=SemanticResult(
                    passed=True, verification_method="exact", unitary_equiv=True
                )
            ),
        )
        == "success"
    )


def test_failed_requirement_does_not_veto_an_oracle_verified_success() -> None:
    """An oracle is ground truth (Principle IV); a planner-extracted
    requirement is not. When they disagree, the planner was wrong — so the
    suite metric stays unchanged rather than being degraded by bad
    extraction."""
    bad_req = RequirementOutcome(
        requirement=Requirement(id="r1", kind="n_qubits", description="d", value=99),
        passed=False,
        detail="circuit has 2 qubits, requirement states 99",
    )
    state = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
    }
    report = _empty_report(
        requirements=[bad_req],
        reference=SemanticResult(passed=True, verification_method="exact", unitary_equiv=True),
    )
    assert terminal_status(state, report) == "success"


def test_failed_requirement_vetoes_success_in_the_product_path() -> None:
    outcome = AssertionOutcome(
        assertion=MeasuresAssertion(qubits=None, expected="00"), passed=True, detail="ok"
    )
    bad_req = RequirementOutcome(
        requirement=Requirement(id="r1", kind="n_qubits", description="d", value=99),
        passed=False,
        detail="circuit has 2 qubits, requirement states 99",
    )
    state = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
        "semantic": None,
    }
    report = _empty_report(assertions=[outcome], requirements=[bad_req])
    assert terminal_status(state, report) == "completed_unverified"


# ---------------------------------------------------------------------------
# finalize / _build_guarantee_report (T096)
# ---------------------------------------------------------------------------


def _done_state(**overrides) -> dict:
    base = {
        "decision": CriticDecision(action="done", rationale="r"),
        "error_history": [],
        "static": StaticResult(parsed=True, executed=True, transpiled=True),
        "assertion_results": None,
        "coupling_map_name": None,
        "resource": None,
    }
    base.update(overrides)
    return base


def test_finalize_returns_status_and_guarantee_report() -> None:
    result = finalize(_done_state())
    # Nothing verified functional correctness on this run, so `status`
    # itself says so — an aggregator reading only this field cannot mistake
    # it for approval.
    assert result["status"] == "completed_unverified"
    report = result["guarantee_report"]
    assert report.executed is True
    assert report.transpiled is True
    assert report.assertions == []
    assert report.coupling_map_name is None
    assert report.topology_respected is None
    assert report.functional_correctness_verified is False  # no assertions declared


def test_finalize_status_and_report_cannot_disagree() -> None:
    """`terminal_status` is handed the SAME report object that is returned,
    not a recomputation of the same conditions — so `status="success"` and
    `functional_correctness_verified=False` can never be emitted together
    in the product path."""
    for state in (_done_state(), _done_state(coupling_map_name="linear_5")):
        result = finalize(state)
        report = result["guarantee_report"]
        if result["status"] == "success":
            assert report.functional_correctness_verified or state.get("semantic") is not None
        else:
            assert not report.functional_correctness_verified


def test_finalize_puts_a_real_guarantee_report_in_state() -> None:
    """The runtime half of the `Any`-typed-field guard: mypy cannot check
    this field, so the type is asserted where the value is constructed."""
    report = finalize(_done_state())["guarantee_report"]
    assert isinstance(report, GuaranteeReport)


def test_finalize_topology_respected_derived_from_static_transpiled() -> None:
    state = _done_state(coupling_map_name="linear_5")
    report = finalize(state)["guarantee_report"]
    assert report.topology_respected is True
    assert report.coupling_map_name == "linear_5"


def test_finalize_no_coupling_map_leaves_topology_respected_none() -> None:
    report = finalize(_done_state())["guarantee_report"]
    assert report.topology_respected is None


def test_finalize_carries_assertion_results_into_the_report() -> None:
    outcome = AssertionOutcome(
        assertion=MeasuresAssertion(qubits=None, expected="00"), passed=True, detail="ok"
    )
    report = finalize(_done_state(assertion_results=[outcome]))["guarantee_report"]
    assert report.assertions == [outcome]
    assert report.functional_correctness_verified is True


def test_finalize_carries_resource_into_the_report() -> None:
    resource = ResourceResult(
        depth=2, cx_count=1, width=2, depth_ratio=1.0, cx_ratio=1.0, passed=True
    )
    report = finalize(_done_state(coupling_map_name="linear_5", resource=resource))[
        "guarantee_report"
    ]
    assert report.resource is resource
