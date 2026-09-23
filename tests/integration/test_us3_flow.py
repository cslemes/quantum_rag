"""T092 — end-to-end tests for User Story 3 (verification without a
reference) through the real graph. See _harness.py for what is real and
what is scripted.

The four acceptance scenarios from spec.md US3, plus the cases that only a
full run exposes: realistic generated code (measurements), what the repair
loop actually shows the generator (FR-012), and verdicts surviving from an
earlier attempt into a later one.
"""

from pathlib import Path

import pytest
from _harness import (
    BELL_CODE,
    BELL_MEASURED_CODE,
    BROKEN_BELL_CODE,
    CRITIC_HINT_JSON,
    IDENTITY_CODE,
    NON_EXECUTING_CODE,
    PHI_MINUS_CODE,
    THREE_QUBIT_CODE,
    assert_status_and_report_agree,
    bell_oracle_loader,
    build,
    fenced,
    planner_json,
    product_state,
)

from qcagent.validators.sandbox import WorkerPool

BELL_ASSERTIONS = (
    "PROBABILITY(|00>) ~= 0.5\n"
    "PROBABILITY(|11>) ~= 0.5\n"
    "PHASE_DIFF(|00>,|11>) ~= 0\n"
    'GATES_SUBSET_OF({"h", "cx"})'
)


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=100) as p:
        yield p


# -- Scenario 1: each assertion evaluated and reported individually -----------


def test_scenario1_each_assertion_evaluated_and_reported_individually(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    result = run.invoke(product_state(BELL_ASSERTIONS))

    assert result["status"] == "success"
    assert run.generator.calls == 1
    assert run.critic.calls == 0
    outcomes = result["assertion_results"]
    assert [o.assertion.kind for o in outcomes] == [
        "amplitude",
        "amplitude",
        "amplitude",
        "gate_restriction",
    ]
    assert all(o.passed is True for o in outcomes)

    report, text = assert_status_and_report_agree(result)
    assert report.assertions == outcomes
    for line in (
        "[PASS] PROBABILITY(|00>) ~= 0.5",
        "[PASS] PROBABILITY(|11>) ~= 0.5",
        "[PASS] PHASE_DIFF(|00>,|11>) ~= 0",
        '[PASS] GATES_SUBSET_OF({"cx", "h"})',
    ):
        assert line in text


def test_scenario1_realistic_code_with_measurements(pool: WorkerPool, tmp_path: Path) -> None:
    """Generated code routinely ends in `measure_all()`. The circuit is the
    same Bell state; every assertion about it must still evaluate (not
    crash the graph), and a gate-set restriction must not count `measure`
    or `barrier` as gates the user excluded."""
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_MEASURED_CODE)])

    result = run.invoke(product_state(BELL_ASSERTIONS))

    assert result["status"] == "success", [o.detail for o in result["assertion_results"]]
    assert all(o.passed is True for o in result["assertion_results"])
    assert_status_and_report_agree(result)


def test_scenario1_gate_set_requirement_ignores_measurement(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Same as above for T091: the real 7B planner emitted `['H', 'CX']`
    for a gate-set requirement; a measured circuit using only H and CX must
    satisfy it."""
    gate_set = {"id": "r3", "kind": "gate_set", "description": "H and CX", "value": ["H", "CX"]}
    run = build(
        pool,
        tmp_path,
        planner_responses=[planner_json(2, extra=(gate_set,))],
        generator_responses=[fenced(BELL_MEASURED_CODE)],
    )

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5"))

    gate_set = next(r for r in result["requirement_results"] if r.requirement.kind == "gate_set")
    assert gate_set.passed is True, gate_set.detail
    assert result["status"] == "success"
    assert_status_and_report_agree(result)


# -- Scenario 2: a failure enters the repair loop, with the assertion NAMED ---


def test_scenario2_violated_assertion_is_named_in_the_repair_loop(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(BROKEN_BELL_CODE), fenced(BELL_CODE)],
        critic_responses=[CRITIC_HINT_JSON],
    )

    result = run.invoke(product_state("PROBABILITY(|00>) ~= 0.5\nPROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert run.critic.calls == 1

    # FR-012 is about what reaches the model, so read the prompts. On the
    # broken circuit P(|00>)=0.5 still holds and P(|11>)=0 does not, so a
    # diagnostic that only carries the numbers ("lhs=0 ~= rhs=0.5") cannot
    # tell the generator WHICH assertion failed.
    # Scoped to the failure diagnostic: since T090b every declared assertion
    # also appears in its own section of every prompt, so "named anywhere in
    # the prompt" no longer says anything about what was reported as FAILED.
    retry_prompt = run.generator.prompts[1]
    diagnostic = retry_prompt.split("## Previous failed attempts", 1)[1]
    assert "AssertionViolated" in diagnostic
    assert "PROBABILITY(|11>) ~= 0.5" in diagnostic, diagnostic
    assert "PROBABILITY(|00>) ~= 0.5" not in diagnostic, "the PASSING assertion was named as failed"
    assert "PROBABILITY(|11>) ~= 0.5" in run.critic.prompts[0], run.critic.prompts[0]

    assert_status_and_report_agree(result)


def test_scenario2_persistent_violation_ends_failed_semantic_not_success(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(BROKEN_BELL_CODE)] * 3,
        critic_responses=[CRITIC_HINT_JSON] * 3,
        max_iter=3,
    )

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "failed_semantic"
    assert result["iteration"] == 3
    _, text = assert_status_and_report_agree(result)
    assert "[FAIL] PROBABILITY(|11>) ~= 0.5" in text


# -- Scenario 3: no assertion -> explicitly not verified ------------------------


def test_scenario3_no_assertions_explicitly_not_verified(pool: WorkerPool, tmp_path: Path) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    result = run.invoke(product_state())

    assert result["status"] == "completed_unverified"
    report, text = assert_status_and_report_agree(result)
    assert report.functional_correctness_verified is False
    assert "No assertions were declared" in text
    assert text.index("FUNCTIONAL CORRECTNESS") < text.index("Executed: yes")
    # FR-009 still ran with nothing declared by the user.
    (n_qubits,) = [r for r in report.requirements if r.requirement.kind == "n_qubits"]
    assert n_qubits.passed is True


# -- Scenario 4: malformed or impossible to evaluate -> refused explicitly ----


def test_scenario4_malformed_assertion_refused_before_any_generation(
    pool: WorkerPool, tmp_path: Path
) -> None:
    # Genuinely malformed (no valid comparator). The earlier example here,
    # `PROBABILITY(|0>) ~= 0.5` on a 2-qubit task, is no longer malformed:
    # since T090 it STATES a 1-qubit register, and the user's assertions win.
    run = build(pool, tmp_path, generator_responses=[])

    result = run.invoke(product_state("PROBABILITY(|01>) =! 0.5"))

    assert result["status"] == "rejected_input"
    assert run.generator.calls == 0
    reasons = [t.get("reason") for t in result["trace"] if t.get("node") == "planner"]
    assert any(r and "malformed assertion" in r for r in reasons), reasons


def test_scenario4_one_bad_line_refuses_the_whole_batch(pool: WorkerPool, tmp_path: Path) -> None:
    """FR-013: never silently trimmed down to the lines that parsed."""
    run = build(pool, tmp_path, generator_responses=[])

    result = run.invoke(product_state('PROBABILITY(|00>) ~= 0.5\nGATES_SUBSET_OF({"cxx"})'))

    assert result["status"] == "rejected_input"
    assert run.generator.calls == 0
    assert not result.get("assertions")


def test_scenario4_impossible_to_evaluate_stops_on_repeat_not_at_max_iter(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(IDENTITY_CODE)] * 5,
        critic_responses=[CRITIC_HINT_JSON] * 5,
        max_iter=5,
    )

    result = run.invoke(product_state("PHASE_DIFF(|00>,|11>) ~= 0"))

    assert result["status"] == "assertion_not_evaluable"
    assert result["iteration"] == 2, "must stop on the second consecutive occurrence"
    assert run.critic.calls == 1  # the repeat aborts without an LLM hint
    _, text = assert_status_and_report_agree(result)
    assert "[NOT_EVALUABLE] PHASE_DIFF(|00>,|11>) ~= 0" in text


# -- Verdicts must never outlive the circuit they were about ------------------


def test_assertion_verdicts_from_an_earlier_attempt_do_not_survive_into_the_report(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Attempt 1 (Phi-minus) passes both probability assertions but fails
    the Bell reference, so the loop retries. Attempt 2 never executes. The
    final report is about attempt 2's code: it must not carry attempt 1's
    passing assertions, and it must never say VERIFIED about code that
    didn't run."""
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(PHI_MINUS_CODE), fenced(NON_EXECUTING_CODE)],
        critic_responses=[CRITIC_HINT_JSON],
        oracle_loader=bell_oracle_loader,
        max_iter=2,
    )
    state = product_state("PROBABILITY(|00>) ~= 0.5\nPROBABILITY(|11>) ~= 0.5")
    state["oracle_ref"] = "bell"

    result = run.invoke(state)

    assert result["status"] == "failed_static"
    report, text = assert_status_and_report_agree(result)
    assert report.executed is False
    assert report.assertions == [], "attempt 1's verdicts leaked into attempt 2's report"
    assert report.requirements == [], "attempt 1's requirement checks leaked too"
    assert "FUNCTIONAL CORRECTNESS: VERIFIED" not in text


# -- Requirements (T091) end to end ------------------------------------------


def test_requirement_violation_vetoes_success_without_entering_the_repair_loop(
    pool: WorkerPool, tmp_path: Path
) -> None:
    # gate_set, not n_qubits: a misread n_qubits is now CORRECTED from the
    # user's assertions before generation (T090), so it never reaches this
    # veto — see test_misread_qubit_count_no_longer_rejects_the_users_assertions.
    h_only = {"id": "r3", "kind": "gate_set", "description": "only H", "value": ["h"]}
    run = build(
        pool,
        tmp_path,
        planner_responses=[planner_json(2, extra=(h_only,))],
        generator_responses=[fenced(BELL_CODE)],
    )

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "completed_unverified"
    assert run.generator.calls == 1, "a requirement violation must not trigger a retry"
    _, text = assert_status_and_report_agree(result)
    assert "[FAIL] gate_set — circuit uses gate(s) outside the required set: ['cx']" in text
    assert "directly checkable" in text


def test_product_path_never_loads_an_oracle_even_with_a_coupling_map(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """`oracle_loader_never_called` fails the test if semantic_check or
    resource_check is reached without a reference."""
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5", coupling_map_name="linear_5"))

    assert result["status"] == "success"
    report, _ = assert_status_and_report_agree(result)
    assert report.topology_respected is True
    assert report.resource is None


# -- The user's assertions are the source of truth for the register (T090) ----


def test_misread_qubit_count_is_corrected_by_two_agreeing_assertions(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """The planner reads the 2-qubit Bell task as 3 qubits; two assertions
    agree on 2. That used to end `rejected_input` with the user's assertion
    called "malformed". Now the assertions win, the requirement is corrected
    (so neither the generator nor T091 acts on the misreading), and the
    correction is stated in the guarantee report, not only in the trace."""
    run = build(
        pool, tmp_path, planner_responses=[planner_json(3)], generator_responses=[fenced(BELL_CODE)]
    )

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5\nPROBABILITY(|00>) ~= 0.5"))

    assert result["status"] == "success"
    planner_trace = next(t for t in result["trace"] if t.get("node") == "planner")
    assert planner_trace["n_qubits_corrected"] == {
        "planner_n_qubits": 3,
        "assertions_n_qubits": 2,
        "supporting_assertions": 2,
    }
    assert "[corrected: the planner read 3 qubits" in run.generator.prompts[0]
    report, text = assert_status_and_report_agree(result)
    assert "[PASS] n_qubits — circuit has 2 qubits, requirement states 2" in text
    assert (
        "Qubit count: 2, taken from 2 of your assertions — the description was read as 3 qubits."
        in text
    )


def test_one_assertion_contradicting_the_planner_asks_instead_of_picking(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, planner_responses=[planner_json(3)], generator_responses=[])

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "rejected_input"
    assert run.generator.calls == 0
    reasons = [t.get("reason") for t in result["trace"] if t.get("node") == "planner"]
    assert any(r and r.startswith("ambiguous qubit count") for r in reasons), reasons


def test_assertions_that_disagree_among_themselves_are_refused(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[])

    result = run.invoke(product_state('PROBABILITY(|11>) ~= 0.5\nMEASURES == "010"'))

    assert result["status"] == "rejected_input"
    assert run.generator.calls == 0
    reasons = [t.get("reason") for t in result["trace"] if t.get("node") == "planner"]
    assert any(r and "disagree among themselves" in r for r in reasons), reasons


def test_circuit_of_the_wrong_width_is_a_named_violation_that_gets_fixed(
    pool: WorkerPool, tmp_path: Path
) -> None:
    """Before the width check, a 3-qubit circuit PASSED `PROBABILITY(|11>) ~=
    0.5` by reading |011>. Now it is a violation that names the mismatch,
    and the retry prompt carries it."""
    run = build(
        pool,
        tmp_path,
        generator_responses=[fenced(THREE_QUBIT_CODE), fenced(BELL_CODE)],
        critic_responses=[CRITIC_HINT_JSON],
    )

    result = run.invoke(product_state("PROBABILITY(|11>) ~= 0.5"))

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert "assertion is written for 2 qubits but the circuit has 3" in run.generator.prompts[1]
    assert_status_and_report_agree(result)


# -- Assertions reach the generator from the first attempt (T090b) -------------


def test_generator_sees_the_declared_assertions_on_its_first_attempt(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    run.invoke(product_state("PROBABILITY(|00>) ~= 0.5\nPHASE_DIFF(|00>,|11>) ~= 0"))

    first = run.generator.prompts[0]
    assert "## Assertions the circuit must satisfy" in first
    assert "- PROBABILITY(|00>) ~= 0.5" in first
    assert "- PHASE_DIFF(|00>,|11>) ~= 0" in first


def test_generator_prompt_has_no_assertion_section_when_none_were_declared(
    pool: WorkerPool, tmp_path: Path
) -> None:
    run = build(pool, tmp_path, generator_responses=[fenced(BELL_CODE)])

    run.invoke(product_state())

    assert "Assertions" not in run.generator.prompts[0]
