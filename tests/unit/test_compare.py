"""Tests for analysis/compare.py (T101, FR-027, SC-008) — the point of this
module is that a regression is named per task, not averaged away."""

from analysis.compare import compare, render
from tests.unit.test_metrics import _record


def test_regression_is_named_not_averaged_away() -> None:
    """Two runs with the SAME aggregate success rate, one task broken and a
    different one fixed. An aggregate reports no change; this must report
    both by name."""
    before = [_record("success", task_id="a"), _record("failed_semantic", task_id="b")]
    after = [_record("failed_semantic", task_id="a"), _record("success", task_id="b")]

    result = compare(before, after)

    assert [c.task_id for c in result.regressed] == ["a"]
    assert [c.task_id for c in result.improved] == ["b"]
    assert result.divergence_rate == 1.0
    assert "REGRESSED" in render(result)


def test_identical_runs_show_no_divergence() -> None:
    runs = [_record("success", task_id="a"), _record("failed_static", task_id="b")]
    result = compare(runs, list(runs))

    assert result.regressed == [] and result.improved == []
    assert result.divergence_rate == 0.0


def test_completed_unverified_does_not_count_as_passing() -> None:
    before = [_record("success", task_id="a")]
    after = [_record("completed_unverified", task_id="a")]

    result = compare(before, after)

    assert [c.task_id for c in result.regressed] == ["a"], (
        "a run that verified nothing must not read as still passing"
    )


def test_seed_level_change_with_same_pass_count_is_still_reported() -> None:
    before = [_record("success", task_id="a", seed=1), _record("aborted", task_id="a", seed=2)]
    after = [_record("aborted", task_id="a", seed=1), _record("success", task_id="a", seed=2)]

    result = compare(before, after)

    assert result.regressed == [] and result.improved == []
    assert [c.task_id for c in result.changed_without_net_effect] == ["a"]
    assert result.divergence_rate == 1.0


def test_tasks_missing_from_one_run_are_flagged_not_silently_dropped() -> None:
    result = compare([_record("success", task_id="a")], [_record("success", task_id="b")])

    assert result.tasks_in_both == 0
    assert result.only_before == ["a"] and result.only_after == ["b"]
    assert "NOT comparable" in render(result)
