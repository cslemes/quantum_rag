"""Base against tuned, PER TASK, in the registered form (distill-family-selection-v2.md,
"Registered analytic structure", 2026-10-28). The cross-profile comparison `analysis.compare`
refuses on purpose: there a different profile is a different system; here it is the question.

    python -m analysis.cross_profile results/<base>/runs.jsonl results/<tuned>/runs.jsonl
    python -m analysis.cross_profile results/<base>/runs.jsonl          # base description only

Nothing here is chosen after the numbers. Fixed before any run and only implemented here:
  * bins: bench/adjacency_bins.json, strict adjacency, 0 / 1 / 2+ (2 and 3+ collapsed);
    sensitivity: general adjacency, 1 against 2+ (its bin 0 has one task and is dropped);
  * PRIMARY: the ordinal depth attempt 1 reaches (0..4), paired change tuned - base per task,
    mean and bootstrap 95% interval per bin;
  * SECONDARY: compila@1 per bin (attempt 1 reached level 3 or 4);
  * NEGATIVE CONTROL: sigma_code, the share of failures whose five attempts emitted
    byte-identical code (the generator events' `code_sha256_16` in the trace);
  * success per bin: description only.

Every controlled field except the profile must agree between the two runs (same server build,
corpus, protocol, host), exactly as `analysis.compare` demands; a mismatch refuses.

A task with no generator call (the planner rejected or aborted the input) has no attempt 1 and
therefore no depth; it is left out of the paired analysis on whichever side it happens and is
listed. That rule is NOT in the registration (which does not mention the case) and is stated
in the output every time.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

from analysis.compare import CONTROLLED_FIELDS, IncomparableRunsError
from bench.runner import iter_records
from bench.schema import RunRecord

BINS_FILE = Path(__file__).resolve().parent.parent / "bench" / "adjacency_bins.json"
BOOTSTRAP_SAMPLES = 10_000
BOOTSTRAP_SEED = 20261028  # the registration date; fixed so the interval is reproducible

LEVEL_0 = {"DeprecatedAPI", "GenerationTruncated"}
LEVEL_1 = {"MissingImport", "UnknownSymbol", "HallucinatedSymbol", "QubitIndexError"}
LEVEL_2 = {"TranspilationFailure", "CircuitSerializationFailure"}
#: `ast.parse` text ends in "(<unknown>, line N)"; the sandbox fallback is stderr, "ExcName: ..."
AST_PARSE = re.compile(r"\(<unknown>, line \d+\)\s*$")


def _level_of_error(error: dict[str, Any]) -> int:
    kind, stage = error.get("error_type"), error.get("stage")
    if stage in ("semantic", "resource") or kind == "ParameterBindingError":
        return 3
    if kind in LEVEL_0:
        return 0
    if kind == "SyntaxError":
        return 0 if AST_PARSE.search(str(error.get("message") or "")) else 1
    if kind in LEVEL_1:
        return 1
    if kind in LEVEL_2:
        return 2
    raise ValueError(f"attempt-1 error with no registered level: stage={stage!r} type={kind!r}")


def attempted(record: RunRecord) -> bool:
    return any(e.get("node") == "generator" for e in record.trace)


def depth_at_1(record: RunRecord) -> int | None:
    """0 did not parse, 1 did not execute, 2 did not transpile, 3 failed semantic/resource,
    4 passed attempt 1. None: no attempt was made."""
    if not attempted(record):
        return None
    first = [e for e in record.error_history if e.get("iteration") == 1]
    return min(map(_level_of_error, first)) if first else 4


def stuck(record: RunRecord) -> bool:
    """Five attempts, one code."""
    hashes = [e.get("code_sha256_16") for e in record.trace if e.get("node") == "generator"]
    return len(hashes) == 5 and len(set(hashes)) == 1


def load_bins(kind: str) -> dict[str, list[str]]:
    bins = json.loads(BINS_FILE.read_text(encoding="utf-8"))[kind]["bins"]
    return {"0": bins["0"], "1": bins["1"], "2+": bins["2"] + bins["3+"]}


def _one_seed(records: list[RunRecord]) -> dict[str, RunRecord]:
    by_task: dict[str, RunRecord] = {}
    for r in records:
        if r.task_id in by_task:
            raise IncomparableRunsError(
                f"{r.task_id} appears more than once: the registered analysis is one seed per task"
            )
        by_task[r.task_id] = r
    return by_task


#: Owner's decision, 2026-11-15: each `docker run` names its container at random, so `hostname`
#: differs between any two containerised runs of the same image on the same machine (two base
#: runs that differed in nothing else were identical on 120/120 tasks: status, every attempt's
#: code, error sequence). A difference in it is DECLARED in the output instead of refusing. Only
#: here: `analysis.compare` still refuses, and every other controlled field still must agree.
DECLARED_NOT_REFUSED = ("hostname",)


def check_same_conditions(base: list[RunRecord], tuned: list[RunRecord]) -> list[str]:
    """Refuses on a controlled difference; returns the declared ones."""
    problems: list[str] = []
    declared: list[str] = []
    for field in CONTROLLED_FIELDS:
        lhs, rhs = base[0].lib_versions.get(field), tuned[0].lib_versions.get(field)
        if lhs is None or rhs is None:
            problems.append(f"{field}: {lhs!r} vs {rhs!r}")
        elif lhs != rhs:
            (declared if field in DECLARED_NOT_REFUSED else problems).append(
                f"{field}: {lhs!r} vs {rhs!r}"
            )
    if base[0].lib_versions.get("profile") == tuned[0].lib_versions.get("profile"):
        problems.append("both runs carry the same profile: use analysis.compare for that")
    if problems:
        raise IncomparableRunsError(
            "base and tuned must differ in the profile and in nothing else controlled:\n  "
            + "\n  ".join(problems)
        )
    return declared


def _bootstrap(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    rng = random.Random(BOOTSTRAP_SEED)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(BOOTSTRAP_SAMPLES))
    return means[int(0.025 * BOOTSTRAP_SAMPLES)], means[int(0.975 * BOOTSTRAP_SAMPLES) - 1]


def describe(run: dict[str, RunRecord], tasks: list[str]) -> dict[str, Any]:
    """One run, one set of tasks."""
    present = [run[t] for t in tasks if t in run]
    made = [r for r in present if attempted(r)]
    depths = [d for d in map(depth_at_1, made) if d is not None]
    failures = [r for r in made if r.status != "success"]
    return {
        "tasks": len(present),
        "no_attempt": sorted(r.task_id for r in present if not attempted(r)),
        "depth_counts": {str(k): depths.count(k) for k in range(5)},
        "depth_mean": sum(depths) / len(depths) if depths else None,
        "compiles_at_1": sum(d >= 3 for d in depths),
        "attempted": len(made),
        "success": sum(r.status == "success" for r in present),
        "failures": len(failures),
        "stuck": sum(map(stuck, failures)),
    }


def paired(base: dict[str, RunRecord], tuned: dict[str, RunRecord], tasks: list[str]) -> dict:
    diffs, left_out = [], []
    for t in tasks:
        b = depth_at_1(base[t]) if t in base else None
        a = depth_at_1(tuned[t]) if t in tuned else None
        if b is None or a is None:
            left_out.append(t)
        else:
            diffs.append(float(a - b))
    interval = _bootstrap(diffs)
    return {
        "n": len(diffs),
        "left_out_no_attempt": left_out,
        "mean_change": sum(diffs) / len(diffs) if diffs else None,
        "ci95": list(interval) if interval else None,
        "up": sum(d > 0 for d in diffs),
        "same": sum(d == 0 for d in diffs),
        "down": sum(d < 0 for d in diffs),
    }


def analyse(base: list[RunRecord], tuned: list[RunRecord] | None) -> dict[str, Any]:
    left = _one_seed(base)
    right = _one_seed(tuned) if tuned else None
    declared: list[str] = []
    if tuned:
        declared = check_same_conditions(base, tuned)
        if set(left) != set(right or {}):
            raise IncomparableRunsError("the two runs do not cover the same tasks")
    out: dict[str, Any] = {
        "base": {k: base[0].lib_versions.get(k) for k in ("profile", "model_digest")},
        "tuned": {k: tuned[0].lib_versions.get(k) for k in ("profile", "model_digest")}
        if tuned
        else None,
        "conditions": {k: base[0].lib_versions.get(k) for k in CONTROLLED_FIELDS}
        | {"qdocs_points_gate": base[0].lib_versions.get("qdocs_points_gate")},
        "declared_differences": declared,
    }
    for kind in ("strict", "general"):
        bins = load_bins(kind)
        if kind == "general":
            bins.pop("0")  # one task: no bin, by registration
        bins = {"all": sorted(left), **bins} if kind == "strict" else bins
        out[kind] = {
            name: {
                "base": describe(left, tasks),
                "tuned": describe(right, tasks) if right else None,
                "paired_depth_change": paired(left, right, tasks) if right else None,
            }
            for name, tasks in bins.items()
        }
    return out


def render(result: dict[str, Any]) -> str:
    def side(d: dict[str, Any] | None) -> str:
        if d is None:
            return "-"
        mean = f"{d['depth_mean']:.2f}" if d["depth_mean"] is not None else "n/a"
        sigma = f"{d['stuck']}/{d['failures']}" if d["failures"] else "0/0"
        return (
            f"depth {mean} {list(d['depth_counts'].values())}  compila@1 {d['compiles_at_1']}/"
            f"{d['attempted']}  sigma_code {sigma}  success {d['success']}/{d['tasks']}"
            + (f"  no attempt: {len(d['no_attempt'])}" if d["no_attempt"] else "")
        )

    lines = [f"base  {result['base']}", f"tuned {result['tuned']}", f"{result['conditions']}"]
    if result["declared_differences"]:
        lines.append(f"DECLARED DIFFERENCES (not refused): {result['declared_differences']}")
    lines.append("depth counts are levels [0,1,2,3,4]; tasks with no generator call have no depth")
    for kind in ("strict", "general"):
        lines += ["", f"== {kind} adjacency" + (" (sensitivity)" if kind == "general" else "")]
        for name, cell in result[kind].items():
            lines.append(f"bin {name}")
            lines.append(f"  base : {side(cell['base'])}")
            if cell["tuned"]:
                lines.append(f"  tuned: {side(cell['tuned'])}")
                p = cell["paired_depth_change"]
                ci = f"[{p['ci95'][0]:+.2f}, {p['ci95'][1]:+.2f}]" if p["ci95"] else "n/a"
                mean = f"{p['mean_change']:+.2f}" if p["mean_change"] is not None else "n/a"
                lines.append(
                    f"  PRIMARY paired depth change (n={p['n']}): mean {mean}, 95% {ci}; "
                    f"up {p['up']} / same {p['same']} / down {p['down']}"
                    + (
                        f"; left out: {p['left_out_no_attempt']}"
                        if p["left_out_no_attempt"]
                        else ""
                    )
                )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", type=Path)
    parser.add_argument("tuned", type=Path, nargs="?")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    base = list(iter_records(args.base))
    tuned = list(iter_records(args.tuned)) if args.tuned else None
    try:
        result = analyse(base, tuned)
    except IncomparableRunsError as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2) if args.json else render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
