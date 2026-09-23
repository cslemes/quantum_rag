"""Compare two regression runs, PER TASK (US7, T101; FR-027, SC-008).

    uv run python -m analysis.compare results/<before>/runs.jsonl results/<after>/runs.jsonl

Aggregates alone cannot answer the question the suite exists for. "The
success rate fell 2%" does not say whether one task broke or five drifted,
and two runs can hold the same rate while swapping which tasks pass. So the
unit here is the task: every task whose outcome changed is named, with
regressions listed first.

SC-008 reads on the same output: two runs of the SAME code and versions
must diverge on ZERO tasks, not "under 5%". The 5% threshold was written
before any measurement existed; measured over two full runs under the
controlled protocol, divergence was 0/360 on every axis (SC-008 as amended,
research.md D20). `divergence_rate` is measured over tasks present in both
runs, and a run comparing different code is expected to diverge — the
criterion is a stability claim about the harness, not a quality claim about
a change.
"""

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel

from bench.runner import iter_records
from bench.schema import RunRecord

# Fields whose equality is what makes a per-task difference MEAN something.
# Measured over two full runs under this protocol, divergence was 0/360 on
# every axis — status, attempt-1 classification, byte-identical `final_code`,
# full error sequence. That zero is not a property of the system alone; it is
# a property of the system RUN THIS WAY:
#
#   ollama_temperature  pinned, never inherited from the Modelfile (F15)
#   qdocs_points        the retrieval corpus is scraped live and drifts (F13)
#   generator_state     the inference server is reset before the run (F19)
#   ollama_num_ctx      silent truncation changes the prompt (D10b)
#
# Comparing runs that disagree on any of these compares two different
# systems, and the per-task diff would read as a regression. An invariant
# that depends on everyone remembering the protocol is one that gets broken
# (F8, F10), so the comparison refuses instead of trusting.
CONTROLLED_FIELDS = (
    "ollama_temperature",
    "qdocs_points",
    "generator_state",
    "ollama_num_ctx",
    # Recorded since the first run, but nothing verified it until now — which
    # is exactly the gap `qdocs_points` had: a recorded field that nothing
    # checks protects nothing. An Ollama upgrade changes generation output,
    # and it is the kind of change that surfaces only when someone
    # reproduces the results later, on another machine or after `apt upgrade`.
    "ollama",
    # WHERE it ran. The largest inherited condition of all, and unrecorded
    # until D15 was amended: verification runs locally, so a different BLAS or
    # CPU dispatch can flip `Operator.equiv()` at a tolerance boundary. Two
    # runs from different environments are two systems, not one system twice.
    "hostname",
    "python",
    "platform",
    "mp_start_method",
    "containerized",
)

# Conditions that change the measurement and that this code CANNOT observe.
# The GPU belongs to the host, `nvidia-smi` is not in the container, and
# Ollama's API exposes neither driver nor CUDA runtime. So `gpu_stack` is
# DECLARED by the operator (`QCAGENT_GPU_STACK`), not detected.
#
# It warns instead of refusing, and the distinction is deliberate rather than
# a softening: a refusal on "unrecorded" would block every comparison anyone
# has ever run, and a gate that always fires teaches people to bypass it —
# the same argument that retired the 5% threshold. A warning states honestly
# that this axis was not verified, which is the true claim.
#
# When the operator DOES declare it, a difference is a hard refusal like any
# other controlled field: undeclared is unverified, declared-and-different is
# incomparable.
DECLARED_FIELDS = ("gpu_stack",)
UNDECLARED = "unrecorded"


class IncomparableRunsError(RuntimeError):
    """Raised when two runs were not produced under the same controlled
    conditions, so a per-task difference cannot be attributed to the change
    under test."""


def check_comparable(before: list[RunRecord], after: list[RunRecord]) -> None:
    """Refuse to compare runs whose controlled conditions differ.

    A MISSING field counts as a mismatch, not as a pass: runs recorded before
    these fields existed cannot be shown to have met the protocol, and
    "absent" must never read as "fine" — the same rule the tri-state verdicts
    follow everywhere else in this project.
    """
    if not before or not after:
        return
    problems = []
    for field in CONTROLLED_FIELDS:
        lhs = before[0].lib_versions.get(field)
        rhs = after[0].lib_versions.get(field)
        if lhs is None or rhs is None:
            problems.append(f"{field}: missing ({lhs!r} vs {rhs!r}) — run predates the protocol")
        elif lhs != rhs:
            problems.append(f"{field}: {lhs!r} != {rhs!r}")
    warnings = []
    for field in DECLARED_FIELDS:
        lhs = before[0].lib_versions.get(field, UNDECLARED)
        rhs = after[0].lib_versions.get(field, UNDECLARED)
        if lhs == UNDECLARED or rhs == UNDECLARED:
            warnings.append(
                f"{field}: not declared on at least one side ({lhs!r} vs {rhs!r}) — this axis "
                f"was NOT verified; set QCAGENT_GPU_STACK to make it checkable"
            )
        elif lhs != rhs:
            problems.append(f"{field}: {lhs!r} != {rhs!r}")
    for warning in warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    if problems:
        raise IncomparableRunsError(
            "these two runs were not produced under the same controlled conditions, so a "
            "per-task difference cannot be attributed to the change under test:\n  "
            + "\n  ".join(problems)
            + "\nRe-run both sides under the same protocol (cold `.cache/llm`, same corpus)."
        )


# A task counts as passing for a seed only when something real about
# functional correctness was verified and passed — `completed_unverified` is
# not success anywhere in this project, least of all in a comparison.
PASSING = "success"


class TaskComparison(BaseModel):
    task_id: str
    before: dict[int, str]  # seed -> status
    after: dict[int, str]
    before_passes: int
    after_passes: int

    @property
    def regressed(self) -> bool:
        return self.after_passes < self.before_passes

    @property
    def improved(self) -> bool:
        return self.after_passes > self.before_passes

    @property
    def changed(self) -> bool:
        return self.before != self.after


class RunComparison(BaseModel):
    tasks_in_both: int
    only_before: list[str]
    only_after: list[str]
    regressed: list[TaskComparison]
    improved: list[TaskComparison]
    changed_without_net_effect: list[TaskComparison]
    divergence_rate: float  # share of shared tasks whose per-seed statuses differ


def _by_task(records: Iterable[RunRecord]) -> dict[str, dict[int, str]]:
    grouped: dict[str, dict[int, str]] = {}
    for record in records:
        grouped.setdefault(record.task_id, {})[record.seed] = record.status
    return grouped


def compare(before: Iterable[RunRecord], after: Iterable[RunRecord]) -> RunComparison:
    left, right = _by_task(before), _by_task(after)
    shared = sorted(set(left) & set(right))

    comparisons = [
        TaskComparison(
            task_id=task_id,
            before=left[task_id],
            after=right[task_id],
            before_passes=sum(1 for s in left[task_id].values() if s == PASSING),
            after_passes=sum(1 for s in right[task_id].values() if s == PASSING),
        )
        for task_id in shared
    ]
    changed = [c for c in comparisons if c.changed]
    return RunComparison(
        tasks_in_both=len(shared),
        only_before=sorted(set(left) - set(right)),
        only_after=sorted(set(right) - set(left)),
        regressed=[c for c in comparisons if c.regressed],
        improved=[c for c in comparisons if c.improved],
        changed_without_net_effect=[c for c in changed if not c.regressed and not c.improved],
        divergence_rate=len(changed) / len(shared) if shared else 0.0,
    )


def render(result: RunComparison) -> str:
    def block(title: str, items: list[TaskComparison]) -> list[str]:
        if not items:
            return [f"{title}: none"]
        return [f"{title}: {len(items)}"] + [
            f"  {c.task_id}: {c.before_passes}/{len(c.before)} -> "
            f"{c.after_passes}/{len(c.after)} passing  {c.before} -> {c.after}"
            for c in items
        ]

    lines = [f"tasks in both runs: {result.tasks_in_both}"]
    if result.only_before or result.only_after:
        lines.append(
            f"NOT comparable — only in before: {result.only_before or 'none'}; "
            f"only in after: {result.only_after or 'none'}"
        )
    lines += [""]
    lines += block("REGRESSED (fewer seeds passing)", result.regressed)
    lines += [""]
    lines += block("improved", result.improved)
    lines += [""]
    lines += block("changed, same number passing", result.changed_without_net_effect)
    lines += [
        "",
        f"divergence: {result.divergence_rate:.1%} of shared tasks changed outcome "
        "(SC-008a: EXACTLY 0% expected between two runs of the SAME code, corpus and "
        "protocol — measured 0/360. Anything above zero is a defect, not tolerance.)",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    before, after = list(iter_records(args.before)), list(iter_records(args.after))
    check_comparable(before, after)
    result = compare(before, after)
    print(result.model_dump_json(indent=2) if args.json else render(result))
    # Exit 1 when anything regressed: this is meant to be usable as a gate
    # before adopting a change (FR-027), not only as a report to read.
    return 1 if result.regressed else 0


if __name__ == "__main__":
    raise SystemExit(main())
