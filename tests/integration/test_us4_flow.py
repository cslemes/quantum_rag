"""T098 — end-to-end tests for User Story 4 (the guarantee report) through
the real graph. See _harness.py for what is real and what is scripted.

spec.md's US4 Independent Test: "for each combination of verifications
executed, check that the report correctly enumerates what was and was not
verified". So beyond the three acceptance scenarios this covers the
combinations the graph can actually produce: product path with and without
assertions, and the regression-suite path (reference comparison) with and
without them.
"""

from pathlib import Path

import pytest
from _harness import (
    BELL_CODE,
    CRITIC_HINT_JSON,
    HEAVY_BELL_CODE,
    PHI_MINUS_CODE,
    assert_status_and_report_agree,
    bell_oracle_loader,
    build,
    fenced,
    planner_json,
    product_state,
)

from qcagent.validators.sandbox import WorkerPool


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=100) as p:
        yield p


def _suite_state(assertions_text: str | None = None) -> dict:
    state = product_state(assertions_text)
    state["oracle_ref"] = "bell"
    return state


# -- Scenario 1: executed + transpiled, no assertions -> NOT verified ---------


def test_scenario1_approved_but_unasserted_circuit_declares_not_verified(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    result = run.invoke(product_state(coupling_map_name="linear_5"))

    assert result["status"] == "completed_unverified"
    report, text = assert_status_and_report_agree(result)
    assert report.executed is True and report.transpiled is True
    assert report.topology_respected is True
    assert "FUNCTIONAL CORRECTNESS: NOT VERIFIED" in text
    assert "nothing about its behavior was checked" in text
    assert "no meaning without one" in text  # depth_ratio without a reference
    # Verdict before every affirmative fact, end to end, not only in a unit test.
    verdict_at = text.index("FUNCTIONAL CORRECTNESS")
    assert verdict_at < text.index("Executed: yes") < text.index("Topology: respects")


# -- Scenario 2: all assertions satisfied -> enumerated, no claim beyond them -


def test_scenario2_satisfied_assertions_enumerated_without_claiming_beyond_them(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    result = run.invoke(product_state("PROBABILITY(|00>) ~= 0.5\nPROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "success"
    _, text = assert_status_and_report_agree(result)
    assert "[PASS] PROBABILITY(|00>) ~= 0.5" in text
    assert "[PASS] PROBABILITY(|11>) ~= 0.5" in text
    assert "it does NOT mean the circuit is correct in any sense beyond those properties" in text
    assert "only the |0...0> input was exercised" in text


# -- Scenario 3: physical device -> "behavior under noise" (T097) -------------


@pytest.mark.skip(
    reason="T097 blocked on US5: nothing executes on a physical device yet, so "
    "hardware_note is never populated. Kept as a visible skip so the gap shows in "
    "every test run instead of being silently absent."
)
def test_scenario3_physical_device_result_labeled_behavior_under_noise() -> None:
    raise AssertionError("unreachable — see skip reason")


# -- Regression-suite path: the report must say a reference WAS compared ------


def test_reference_verified_run_reports_the_reference_check(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """A run that passed exact unitary equivalence against a verified oracle
    DID have its behavior checked. The report must say so; claiming
    "nothing about its behavior was checked" next to status=success is F8's
    divergence in the other direction, and a false statement besides."""
    run = build(
        pool, tmp_path, generator_responses=[fenced(BELL_CODE)], oracle_loader=bell_oracle_loader
    )

    result = run.invoke(_suite_state())

    assert result["status"] == "success"
    report, text = assert_status_and_report_agree(result)
    assert report.functional_correctness_verified is True
    assert "nothing about its behavior was checked" not in text
    assert "reference" in text.split("\n")[2].lower()
    assert "exact" in text


def test_reference_and_assertions_both_reported(pool: WorkerPool, tmp_path: Path) -> None:
    run = build(
        pool, tmp_path, generator_responses=[fenced(BELL_CODE)], oracle_loader=bell_oracle_loader
    )

    result = run.invoke(_suite_state("PROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "success"
    _, text = assert_status_and_report_agree(result)
    assert "[PASS] PROBABILITY(|11>) ~= 0.5" in text
    assert "reference" in text.lower()


def test_requirement_disagreeing_with_a_verified_reference_does_not_veto_it(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """An oracle is ground truth (Principle IV); a planner-extracted
    requirement is not. The disagreement is still shown, but the planner
    was wrong, so the run is still verified — and the suite metric stays
    unchanged."""
    run = build(
        pool,
        tmp_path,
        planner_responses=[planner_json(3)],
        generator_responses=[fenced(BELL_CODE)],
        oracle_loader=bell_oracle_loader,
    )

    result = run.invoke(_suite_state())

    assert result["status"] == "success"
    _, text = assert_status_and_report_agree(result)
    assert "[FAIL] n_qubits" in text


def test_resource_cutoff_after_a_passed_reference_is_verified_but_not_success(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """The one honest case of VERIFIED alongside a non-success status: the
    circuit IS equivalent to the reference, and the loop ran out of attempts
    trying to make it lighter. The report must say both — functional
    correctness verified, resources EXCEED the limit — and `status` must not
    say success, because the run did not meet its constraints."""
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(HEAVY_BELL_CODE)] * 2,
        critic_responses=[CRITIC_HINT_JSON] * 2,
        oracle_loader=bell_oracle_loader,
        max_iter=2,
        resource_opt_level=0,
    )

    result = run.invoke(_suite_state())

    assert result["status"] == "aborted"
    report, text = assert_status_and_report_agree(result)
    assert report.functional_correctness_verified is True
    assert "EXCEEDS the configured limit" in text


def test_failed_reference_is_never_outranked_by_passing_assertions(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Phi-minus passes both probability assertions (it has the same |00>/|11>
    probabilities as Bell) but is NOT the Bell unitary. The verified reference
    says the circuit is wrong; partial user properties saying nothing is wrong
    must not turn that into VERIFIED. Reachable exactly this way: assertions
    pass, the reference keeps failing, the loop aborts."""
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(PHI_MINUS_CODE)],
        oracle_loader=bell_oracle_loader,
        max_iter=1,
    )

    result = run.invoke(_suite_state("PROBABILITY(|00>) ~= 0.5\nPROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "failed_semantic"
    report, text = assert_status_and_report_agree(result)
    assert report.functional_correctness_verified is False
    assert "does not match the verified reference" in text.splitlines()[2]
    assert "Reference comparison: FAILED" in text
