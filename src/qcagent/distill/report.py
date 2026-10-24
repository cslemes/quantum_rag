"""Read a pilot's records back into its report: acceptance by family, tokens
(reasoning separately), spend against the estimate, and the serving-model check.

Records are append-only facts; this reads them, it never changes them. A
statement's verdict is its LATEST record; its cost is that of the call that was
actually paid for (a re-check after an infrastructure fault is answered from the
cache and costs nothing, so the earlier record's cost stands).
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from qcagent.distill.pilot import LABEL


def pilot_report(out_dir: Path) -> dict[str, Any]:
    records = [json.loads(x) for x in (out_dir / "records.jsonl").read_text().splitlines() if x]
    meta = json.loads((out_dir / "dataset_meta.json").read_text())
    requested = meta["identity"]["model"]
    latest: dict[str, dict[str, Any]] = {}
    paid: dict[str, dict[str, Any]] = {}
    for record in records:
        latest[record["statement_id"]] = record
        if record["cost"]["source"] != "cache":
            paid[record["statement_id"]] = record
    families: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "statements": 0,
            "accepted": 0,
            "rejections": Counter(),
            "tokens": Counter(),
            "usd": 0.0,
        }
    )
    for record in latest.values():
        f = families[record["family"]]
        f["statements"] += 1
        f["accepted"] += record["label"] == LABEL
        if record["reject_reason"]:
            f["rejections"][record["reject_reason"]] += 1
    for record in paid.values():
        f = families[record["family"]]
        usage = record["provenance"]["derived"]["usage"]
        details = usage.get("completion_tokens_details")
        reasoning = details.get("reasoning_tokens", 0) if isinstance(details, dict) else 0
        if not isinstance(details, dict):
            f["tokens"]["reasoning_not_reported_calls"] += 1
        f["tokens"]["input"] += record["tokens"]["input"]
        f["tokens"]["output_total"] += record["tokens"]["output"]
        f["tokens"]["reasoning"] += reasoning
        f["tokens"]["visible"] += record["tokens"]["output"] - reasoning
        f["usd"] += record["cost"]["usd"]
    # Acceptance BY PROVIDER: the model id is pinned, the host that served a call is
    # not, and the oracle checks correctness only, so a host running a more aggressive
    # quantisation yields correct-but-poor code the filter cannot see. Each call's
    # provider is in its provenance, so one host's examples can be excluded afterwards.
    providers: dict[str, dict[str, int]] = defaultdict(lambda: {"statements": 0, "accepted": 0})
    for sid, record in latest.items():
        host = paid[sid]["provenance"]["derived"]["served_provider"]
        providers[host]["statements"] += 1
        providers[host]["accepted"] += record["label"] == LABEL
    served = Counter(r["provenance"]["derived"]["served_model"] for r in paid.values())
    estimate = meta["first_estimate"]["usd"]
    actual = sum(r["cost"]["usd"] for r in paid.values())
    return {
        "dataset_version": meta["dataset_version"],
        "teacher": meta["identity"],
        "statements": len(latest),
        "accepted": sum(1 for r in latest.values() if r["label"] == LABEL),
        "by_family": {
            name: {
                **{k: v for k, v in f.items() if k not in ("rejections", "tokens", "usd")},
                "acceptance": round(f["accepted"] / f["statements"], 3),
                "rejections": dict(f["rejections"]),
                "tokens": dict(f["tokens"]),
                "usd": round(f["usd"], 6),
            }
            for name, f in families.items()
        },
        "paid_calls": len(paid),
        "rechecked_from_cache": sum(1 for r in records if r.get("retry_of_infrastructure_failure")),
        "actual_usd": round(actual, 6),
        "labelled_estimate_usd": estimate,
        "actual_over_labelled_estimate": round(actual / estimate, 3) if estimate else None,
        "serving_model_counts": dict(served),
        "serving_model_matched_requested_on_all": set(served) == {requested},
        "acceptance_by_provider": dict(providers),
        "providers": dict(
            Counter(r["provenance"]["derived"]["served_provider"] for r in paid.values())
        ),
        "finish_reasons": dict(
            Counter(r["provenance"]["derived"]["finish_reason"] for r in paid.values())
        ),
        "price_windows": dict(Counter(r["cost"]["window"] for r in paid.values())),
    }
