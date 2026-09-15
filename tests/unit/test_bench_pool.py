"""Regression test for scripts/bench_pool.py's interpretation logic — the
part that must say "not amortizing" plainly if the numbers ever show that,
not just print a table and leave the reader to notice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))

from bench_pool import SUITE_CALLS, interpret  # noqa: E402


def test_reports_amortization_when_first_submit_is_much_slower() -> None:
    results = [(1.5, 0.001)] + [(0.0006, 0.0004)] * 19

    text = interpret(results)

    assert "consistent with D1b" in text
    assert "WARNING" not in text
    assert f"{SUITE_CALLS:,} calls" in text


def test_warns_plainly_when_every_submit_pays_the_same_overhead() -> None:
    """The failure mode this whole script exists to catch: workers being
    recreated per call instead of reused, so the pool provides no benefit.
    """
    results = [(0.9, 0.001)] * 20

    text = interpret(results)

    assert "WARNING" in text
    assert "no amortization benefit" in text.lower() or "no amortization" in text.lower()
    assert "consistent with D1b" not in text


def test_borderline_delta_below_threshold_is_treated_as_no_amortization() -> None:
    """A delta smaller than the 0.5s threshold is noise, not evidence of
    the ~1-2s import cost D1b documents — must not be reported as success."""
    results = [(0.01, 0.001)] + [(0.006, 0.001)] * 19

    text = interpret(results)

    assert "WARNING" in text
