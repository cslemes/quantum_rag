"""Regression-suite metrics (US7, T059/T059b/T060/T061).

    uv run python -m analysis.metrics results/<run_id>/runs.jsonl   # or: make report

Reads a run's append-only JSONL and reports each metric SEPARATELY (FR-025):
one blended "score" would hide which layer regressed, which is the only
question a regression suite exists to answer.

Two denominators, deliberately distinct:

* `attempted` excludes `status="infrastructure_error"` (T059b). A pool
  timeout, a Qdrant outage or an unreachable provider is not a failure of the
  generator, and leaving those in the denominator makes the system look worse
  the flakier the infrastructure is. They are reported on their own as
  `infrastructure_error_rate`, over ALL runs, so excluding them can never
  hide them.
* `verified` counts runs where something real about functional correctness
  was verified and passed (`status="success"`). `completed_unverified` is
  counted apart and never folded in — that distinction is the whole point of
  the status split (data-model.md), and a metrics table that collapsed the
  two would re-introduce the over-claim the split removed.
"""

import argparse
import statistics
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel

from bench.runner import iter_records
from bench.schema import RunRecord, TaskSpec

TASKS_DIR = Path("bench/tasks")


def load_task_tiers(tasks_dir: Path = TASKS_DIR) -> dict[str, str]:
    return {
        spec.task_id: spec.tier
        for spec in (
            TaskSpec.model_validate_json(p.read_text()) for p in sorted(tasks_dir.rglob("*.json"))
        )
    }


def _first_attempt_reached(record: RunRecord, stage: str) -> bool:
    """True when attempt 1 produced no error at `stage` — the "@1" metrics
    are about the FIRST attempt, not about what the retry loop eventually
    rescued."""
    return not any(
        error.get("iteration") == 1 and error.get("stage") == stage
        for error in record.error_history
    )


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


class SuiteMetrics(BaseModel):
    runs: int
    attempted: int  # runs minus infrastructure AND harness errors — the denominator (T059b)
    infrastructure_errors: int
    infrastructure_error_rate: float  # over ALL runs, never hidden by the exclusion
    # Runs that raised an unexpected exception — OUR defect, not the world's
    # and not the generator's. Excluded from `attempted` for the same reason
    # infrastructure errors are, but reported far more loudly: any nonzero
    # value means the suite hit a bug in itself, and the numbers beside it
    # describe a run that did not complete as designed.
    harness_errors: int

    compiles_at_1: float | None  # attempt 1 executed and transpiled
    verified_at_1: float | None  # attempt 1 both verified and passed
    success_rate: float | None  # verified and passed, any attempt
    completed_unverified_rate: float | None  # finished clean, nothing verified
    success_rate_by_tier: dict[str, float]
    status_counts: dict[str, int]

    mean_fidelity: float | None  # distributional oracles only
    mean_iterations_to_success: float | None
    mean_depth_ratio: float | None
    mean_cx_ratio: float | None
    mean_latency_s_resolved: float | None
    total_cost_usd: float


def compute(records: Iterable[RunRecord], tiers: dict[str, str] | None = None) -> SuiteMetrics:
    all_records = list(records)
    tiers = tiers if tiers is not None else {}
    infra = sum(1 for r in all_records if r.status == "infrastructure_error")
    harness = sum(1 for r in all_records if r.status == "harness_error")
    attempted = [
        r for r in all_records if r.status not in ("infrastructure_error", "harness_error")
    ]

    def rate(count: int) -> float | None:
        return count / len(attempted) if attempted else None

    successes = [r for r in attempted if r.status == "success"]
    by_tier: dict[str, list[RunRecord]] = {}
    for record in attempted:
        by_tier.setdefault(tiers.get(record.task_id, "unknown"), []).append(record)

    status_counts: dict[str, int] = {}
    for record in all_records:
        status_counts[record.status] = status_counts.get(record.status, 0) + 1

    fidelities = [
        r.semantic["hellinger_fidelity"]
        for r in attempted
        if r.semantic and r.semantic.get("hellinger_fidelity") is not None
    ]
    # `is not None`, not a bare truthiness or presence check. A ratio can be
    # legitimately absent — `cx_ratio` is None whenever the REFERENCE has no
    # CX gates, where the ratio is undefined rather than zero — and feeding
    # that None into `fmean` raised `TypeError: must be real number, not
    # NoneType`, which would have crashed the report at the exact moment a
    # three-hour run finished. Third instance of N/A-treated-as-a-value in
    # this codebase, after T099's `if not verdict` and the reference checks
    # in F11: a tri-state collapsed into two states, in whichever direction
    # the surrounding code happened to assume.
    #
    # 0.0 is also a real, meaningful ratio, so anything that drops falsy
    # values here would silently bias the mean upward.
    depth_ratios = [
        r.resource["depth_ratio"]
        for r in attempted
        if r.resource and r.resource.get("depth_ratio") is not None
    ]
    cx_ratios = [
        r.resource["cx_ratio"]
        for r in attempted
        if r.resource and r.resource.get("cx_ratio") is not None
    ]

    return SuiteMetrics(
        runs=len(all_records),
        attempted=len(attempted),
        infrastructure_errors=infra,
        infrastructure_error_rate=infra / len(all_records) if all_records else 0.0,
        harness_errors=harness,
        compiles_at_1=rate(sum(1 for r in attempted if _first_attempt_reached(r, "static"))),
        verified_at_1=rate(sum(1 for r in successes if r.iterations == 1)),
        success_rate=rate(len(successes)),
        completed_unverified_rate=rate(
            sum(1 for r in attempted if r.status == "completed_unverified")
        ),
        success_rate_by_tier={
            tier: sum(1 for r in rs if r.status == "success") / len(rs)
            for tier, rs in sorted(by_tier.items())
        },
        status_counts=status_counts,
        mean_fidelity=_mean(fidelities),
        mean_iterations_to_success=_mean([float(r.iterations) for r in successes]),
        mean_depth_ratio=_mean(depth_ratios),
        mean_cx_ratio=_mean(cx_ratios),
        mean_latency_s_resolved=_mean([r.latency_s for r in attempted]),
        total_cost_usd=sum(r.cost_usd for r in all_records),
    )


def render(metrics: SuiteMetrics) -> str:
    def pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.1%}"

    lines: list[str] = []
    if metrics.harness_errors:
        # First thing on the page, before any rate a reader might quote. A
        # run that hit our own bugs is not a baseline, and saying so after
        # the numbers would be saying it too late.
        lines += [
            f"!! {metrics.harness_errors} HARNESS ERROR(S) — the suite hit a bug in ITSELF on "
            f"{metrics.harness_errors} of {metrics.runs} runs.",
            "!! These are excluded from the denominator below, so the rates describe only the "
            "runs that actually ran.",
            "!! This is NOT a clean baseline: fix the defect and re-run before comparing "
            "anything against these numbers.",
            "",
        ]
    lines += [
        f"runs: {metrics.runs}  (attempted: {metrics.attempted}, "
        f"infrastructure errors excluded: {metrics.infrastructure_errors}, "
        f"harness errors excluded: {metrics.harness_errors})",
        f"infrastructure error rate (of all runs): {metrics.infrastructure_error_rate:.1%}",
        "",
        f"compila@1:            {pct(metrics.compiles_at_1)}",
        f"verificado@1:         {pct(metrics.verified_at_1)}",
        f"taxa de sucesso:      {pct(metrics.success_rate)}",
        f"completed_unverified: {pct(metrics.completed_unverified_rate)}  "
        "(finished clean, nothing verified — NOT success)",
        "",
        "taxa de sucesso por tier:",
        *(f"  {tier}: {rate:.1%}" for tier, rate in metrics.success_rate_by_tier.items()),
        "",
        "status counts: " + ", ".join(f"{s}={n}" for s, n in sorted(metrics.status_counts.items())),
        "",
    ]

    def num(label: str, value: float | None, fmt: str = ".3f") -> str:
        return f"{label}: " + ("n/a" if value is None else format(value, fmt))

    lines += [
        num("fidelidade média (oráculos distribucionais)", metrics.mean_fidelity, ".4f"),
        num("iterações até sucesso (média)", metrics.mean_iterations_to_success, ".2f"),
        num("depth_ratio médio", metrics.mean_depth_ratio),
        num("cx_ratio médio", metrics.mean_cx_ratio),
        num("latência média por execução (s)", metrics.mean_latency_s_resolved, ".1f"),
        f"custo total (USD): {metrics.total_cost_usd:.4f}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", type=Path, nargs="?", help="results/<run_id>/runs.jsonl")
    parser.add_argument("--json", action="store_true", help="emit the metrics as JSON")
    args = parser.parse_args(argv)

    jsonl = args.jsonl
    if jsonl is None:
        candidates = sorted(Path("results").glob("*/runs.jsonl"), key=lambda p: p.stat().st_mtime)
        if not candidates:
            print("no results/*/runs.jsonl found — run the suite first", file=sys.stderr)
            return 1
        jsonl = candidates[-1]

    metrics = compute(iter_records(jsonl), load_task_tiers())
    print(metrics.model_dump_json(indent=2) if args.json else f"{jsonl}\n\n{render(metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
