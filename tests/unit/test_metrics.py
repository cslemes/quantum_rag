"""Tests for analysis/metrics.py (T059/T059b) — the two denominator rules
carry the weight here: infrastructure errors never count against the
generator, and `success` is never conflated with `completed_unverified`.
"""

from analysis.metrics import compute, render
from bench.schema import RunRecord

_TIERS = {"a": "t1", "b": "t2"}


def _record(status: str, *, task_id: str = "a", iterations: int = 1, **kw) -> RunRecord:
    defaults = dict(
        run_id="r",
        task_id=task_id,
        model_id="m",
        seed=1,
        status=status,
        iterations=iterations,
        final_code="qc = None",
        static=None,
        semantic=None,
        resource=None,
        error_history=[],
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.01,
        latency_s=1.5,
        git_sha="abc",
        lib_versions={},
        timestamp="2026-09-17T00:00:00+0000",
    )
    defaults.update(kw)
    return RunRecord(**defaults)


def test_infrastructure_errors_leave_the_denominator_but_are_still_reported() -> None:
    records = [_record("success"), _record("failed_semantic"), _record("infrastructure_error")]
    m = compute(records, _TIERS)

    assert m.runs == 3
    assert m.attempted == 2, "infrastructure error must not count against the generator"
    assert m.success_rate == 0.5  # 1 of 2 attempted, not 1 of 3
    assert m.infrastructure_errors == 1
    assert m.infrastructure_error_rate == 1 / 3, "reported over ALL runs, never hidden"


def test_completed_unverified_is_never_counted_as_success() -> None:
    m = compute([_record("success"), _record("completed_unverified")], _TIERS)

    assert m.success_rate == 0.5
    assert m.completed_unverified_rate == 0.5
    assert "completed_unverified" in render(m)
    assert "NOT success" in render(m)


def test_compiles_at_1_reads_the_first_attempt_not_the_rescued_one() -> None:
    """A run that failed static on attempt 1 and was rescued on attempt 2 is
    a success, but it did NOT compile at 1."""
    rescued = _record(
        "success",
        iterations=2,
        error_history=[{"iteration": 1, "stage": "static", "error_type": "SyntaxError"}],
    )
    m = compute([rescued, _record("success")], _TIERS)

    assert m.compiles_at_1 == 0.5
    assert m.success_rate == 1.0
    assert m.verified_at_1 == 0.5, "only the run that succeeded on attempt 1"


def test_success_rate_by_tier_splits_by_task() -> None:
    m = compute(
        [
            _record("success", task_id="a"),
            _record("failed_semantic", task_id="b"),
            _record("success", task_id="b"),
        ],
        _TIERS,
    )
    assert m.success_rate_by_tier == {"t1": 1.0, "t2": 0.5}


def test_secondary_metrics_use_present_values_only() -> None:
    m = compute(
        [
            _record(
                "success",
                semantic={"hellinger_fidelity": 0.98},
                resource={"depth_ratio": 1.5, "cx_ratio": 2.0},
            ),
            _record("success"),
        ],
        _TIERS,
    )
    assert m.mean_fidelity == 0.98
    assert m.mean_depth_ratio == 1.5
    assert m.total_cost_usd == 0.02


def test_empty_run_does_not_divide_by_zero() -> None:
    m = compute([], _TIERS)
    assert m.runs == 0 and m.success_rate is None
    assert "n/a" in render(m)


def test_an_undefined_ratio_is_skipped_not_fed_into_the_mean() -> None:
    """Bug 18. `cx_ratio` is None whenever the REFERENCE has no CX gates —
    the ratio is undefined there, not zero. Feeding that into `fmean` raised
    `TypeError: must be real number, not NoneType`, which would have crashed
    the report at the moment a three-hour run finished.

    Third instance of N/A-treated-as-a-value here, after T099's
    `if not verdict` and the reference checks in F11.
    """
    metrics = compute(
        [
            _record("success", resource={"depth_ratio": 1.0, "cx_ratio": None}),
            _record("success", resource={"depth_ratio": 2.0, "cx_ratio": 3.0}),
        ]
    )

    assert metrics.mean_cx_ratio == 3.0, "the defined value only, not a crash and not a zero"
    assert metrics.mean_depth_ratio == 1.5


def test_a_zero_ratio_still_counts() -> None:
    """The guard must test `is not None`, not truthiness: 0.0 is a real
    ratio, and dropping it would bias the mean upward."""
    metrics = compute(
        [
            _record("success", resource={"depth_ratio": 0.0, "cx_ratio": 0.0}),
            _record("success", resource={"depth_ratio": 2.0, "cx_ratio": 2.0}),
        ]
    )

    assert metrics.mean_cx_ratio == 1.0
    assert metrics.mean_depth_ratio == 1.0
