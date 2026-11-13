"""Judge stored teacher answers again under the current oracle, as a NEW dataset version.

No teacher call is made. This exists because an oracle can be wrong while its statements are
right: train-v1's `qft` family, in the inverse / no-SWAP cell, checked answers against the adjoint
of the no-swap transform while the statement spelled out another matrix (families/qft.py). The
answers were answers to the statement, and the statement did not change, so they are judged again
instead of being bought again.

Rules, none of them optional:
  * the source directory is read, never written. The new directory holds the source registry and
    the source records byte for byte, then ONE appended record per re-judged statement. The latest
    record of a statement wins everywhere (pilot, export), so the new verdict takes effect and the
    old one stays on file above it;
  * the answer is judged by `pilot._score`, the function the generation run uses, on the stored
    `response_text`: one judging path, whoever asks;
  * a re-judged record costs nothing (`cost.usd` 0, source "rejudged") and carries the previous
    verdict and the original cost under `rejudged.previous`, so spend is not counted twice and
    every changed label shows what it was;
  * CONTROL: the answers of the same families that are NOT selected are judged again too and must
    reproduce their stored verdict exactly. One mismatch stops everything before a byte is
    written: it would mean this is not the generation's path, or that the oracle change reaches
    further than the selection says;
  * a sandbox timeout is not a verdict: it is retried, and if it persists nothing is written.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qcagent.distill.families.base import Family, Variation
from qcagent.distill.pilot import INFRASTRUCTURE_PREFIX, _latest_records, _score
from qcagent.validators.sandbox import WorkerPool

#: what `_score` writes; everything else on a record is the call, and is kept as it was
VERDICT_FIELDS = ("code", "static", "acceptance", "leak_check", "label", "reject_reason")
RETRIES = 3


class RejudgeRefused(RuntimeError):
    """Nothing was written: the inputs or the control do not allow a re-judged dataset."""


def _verdict(record: dict[str, Any]) -> tuple[Any, Any]:
    return record.get("label"), record.get("reject_reason")


def _name(verdict: tuple[Any, Any]) -> str:
    return str(verdict[0] or verdict[1])


def judge_again(
    record: dict[str, Any], family: Family, v: Variation, pool: WorkerPool
) -> dict[str, Any]:
    """A copy of `record` with its verdict recomputed from the stored answer."""
    for _ in range(RETRIES):
        again = {k: copy.deepcopy(x) for k, x in record.items() if k not in VERDICT_FIELDS}
        again["label"] = None
        again["reject_reason"] = None
        _score(again, record["response_text"], family, v, pool)
        if not str(again.get("reject_reason") or "").startswith(INFRASTRUCTURE_PREFIX):
            return again
    raise RejudgeRefused(
        f"{record['statement_id']}: the sandbox timed out {RETRIES} times, which is not a verdict"
    )


def rejudge_dataset(
    *,
    source_dir: Path,
    out_dir: Path,
    families: tuple[Family, ...],
    variation_count: int | None,
    pool: WorkerPool,
    dataset_version: str,
    reason: str,
    selects: Callable[[Family, Variation], bool],
) -> dict[str, Any]:
    """Writes `out_dir` (registry, records, dataset_meta, rejudge_summary). Returns the summary.

    `families` are the families whose oracle changed; `selects` says which of their variations
    are re-judged. Their other answers are the control. `variation_count` is how many variations
    each family was admitted with in the source run (it maps a record back to its variation).
    """
    source_records = source_dir / "records.jsonl"
    source_meta = json.loads((source_dir / "dataset_meta.json").read_text(encoding="utf-8"))
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RejudgeRefused(f"{out_dir} is not empty: a re-judged dataset is a new directory")
    if dataset_version == source_meta["dataset_version"]:
        raise RejudgeRefused("a re-judged dataset is a new dataset version, not the source's")
    if not reason.strip():
        raise RejudgeRefused("no reason given: why answers are judged again is part of the data")
    source_bytes = source_records.read_bytes()
    if not source_bytes.endswith(b"\n"):
        raise RejudgeRefused("the source records end in a half-written line")

    by_name = {f.name: f for f in families}
    variations = {
        f.name: {
            v.key: v
            for v in (f.variations() if variation_count is None else f.variations(variation_count))  # type: ignore[call-arg]
        }
        for f in families
    }
    selected: list[tuple[dict[str, Any], Family, Variation]] = []
    control: list[tuple[dict[str, Any], Family, Variation]] = []
    for record in _latest_records(source_records).values():
        family = by_name.get(record["family"])
        if family is None or record.get("response_text") is None:
            continue  # another family, or no answer on file to judge (a provider error)
        v = variations[family.name].get(record["variation_key"])
        if v is None:
            raise RejudgeRefused(
                f"{record['statement_id']}: its variation is not among the first "
                f"{variation_count} of {family.name}; wrong --admitted?"
            )
        (selected if selects(family, v) else control).append((record, family, v))
    if not selected:
        raise RejudgeRefused("the selection matches no answer on file")

    mismatches = []
    for record, family, v in control:
        again = judge_again(record, family, v, pool)
        if _verdict(again) != _verdict(record):
            mismatches.append(
                f"{record['statement_id']}: {_name(_verdict(record))} -> {_name(_verdict(again))}"
            )
    if mismatches:
        raise RejudgeRefused(
            f"{len(mismatches)} of {len(control)} control answers changed verdict, e.g. "
            f"{mismatches[:5]}: the change reaches beyond the selection, or this is not the "
            "generation's judging path. Nothing written."
        )

    appended: list[dict[str, Any]] = []
    changes: Counter[str] = Counter()
    for record, family, v in selected:
        again = judge_again(record, family, v, pool)
        again["cost"] = {"usd": 0.0, "source": "rejudged", "window": None}
        again["rejudged"] = {
            "from_dataset_version": source_meta["dataset_version"],
            "reason": reason,
            "previous": {
                k: record.get(k)
                for k in ("label", "reject_reason", "acceptance", "leak_check", "cost")
            },
        }
        appended.append(again)
        changes[f"{_name(_verdict(record))} -> {_name(_verdict(again))}"] += 1

    out_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_dir / "registry.jsonl", out_dir / "registry.jsonl")
    rejects = source_dir / "registry.rejects.jsonl"
    if rejects.exists():
        shutil.copyfile(rejects, out_dir / rejects.name)
    with (out_dir / "records.jsonl").open("wb") as sink:
        sink.write(source_bytes)
        for record in appended:
            sink.write((json.dumps(record) + "\n").encode())
    accepted: Counter[str] = Counter(
        r["family"] for r in _latest_records(out_dir / "records.jsonl").values() if r.get("label")
    )
    derived = {
        "dataset_version": source_meta["dataset_version"],
        "records_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "reason": reason,
        "families": sorted(by_name),
        "rejudged_statements": len(appended),
        "control_statements": len(control),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    meta = {**source_meta, "dataset_version": dataset_version, "derived_from": derived}
    (out_dir / "dataset_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary = {
        "dataset_version": dataset_version,
        "derived_from": derived,
        "verdict_changes": dict(sorted(changes.items())),
        "control": {"judged_again": len(control), "changed": 0},
        "accepted_per_family": dict(sorted(accepted.items())),
        "teacher_calls": 0,
    }
    (out_dir / "rejudge_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return summary
