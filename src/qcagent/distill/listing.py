"""The OpenRouter model listing, as evidence about the pinned teacher.

`GET /api/v1/models` is public and carries, per model: the id, the
`canonical_slug` (the dated release the id resolves to), the Hugging Face id of
the weights (so the author's licence can be found), the supported reasoning
efforts, and the pricing including its time-of-day overrides. Three uses:

* the SNAPSHOT: the id is recorded together with the canonical slug it resolves
  to. A response may name either as the serving model, so both are accepted;
  anything else is a different model. If a later run finds the same id resolving
  to a different canonical slug, the dataset refuses it (it is another teacher);
* the EFFORT: the pinned effort must be one the model lists;
* the RATES: the peak windows and prices in `spend.py` were operator-stated; the
  listing is read at run start and any discrepancy is recorded, not ignored.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from typing import Any

from qcagent.distill.spend import PEAK_UTC_HOURS, RATES_USD_PER_MTOK

LISTING_URL = "https://openrouter.ai/api/v1/models"
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


class SnapshotNotListed(RuntimeError):
    """The pinned model id is not in the listing."""


def fetch_listing(url: str = LISTING_URL, *, timeout: float = 30.0) -> list[dict[str, Any]]:
    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - fixed https URL
        return json.load(response)["data"]


def listing_entry(model_id: str, fetch: Callable[[], list[dict[str, Any]]] = fetch_listing) -> dict:
    for entry in fetch():
        if entry["id"] == model_id:
            return entry
    raise SnapshotNotListed(f"{model_id!r} is not in the OpenRouter model listing")


def snapshot_facts(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entry["id"],
        "canonical_slug": entry["canonical_slug"],
        "hugging_face_id": entry.get("hugging_face_id"),
        "supported_efforts": (entry.get("reasoning") or {}).get("supported_efforts"),
        "default_effort": (entry.get("reasoning") or {}).get("default_effort"),
        "listed_pricing": entry.get("pricing"),
    }


def accepted_served_models(facts: dict[str, Any]) -> set[str]:
    return {facts["id"], facts["canonical_slug"]}


def effort_problems(facts: dict[str, Any], effort: str) -> list[str]:
    efforts = facts.get("supported_efforts")
    if efforts is None:
        return ["the listing states no supported reasoning efforts"]
    return [] if effort in efforts else [f"effort {effort!r} not in the listed {efforts}"]


def rate_discrepancies(facts: dict[str, Any]) -> list[str]:
    """Compare the listing's peak windows and prices with the ones `spend.py` uses."""
    pricing = facts.get("listed_pricing") or {}
    problems: list[str] = []

    def per_mtok(value: Any) -> float:
        return round(float(value) * 1_000_000, 6)

    off_in, off_out = RATES_USD_PER_MTOK["off-peak"]
    if (per_mtok(pricing["prompt"]), per_mtok(pricing["completion"])) != (off_in, off_out):
        problems.append(f"base price {pricing['prompt']}/{pricing['completion']} per token")
    peak_in, peak_out = RATES_USD_PER_MTOK["peak"]
    windows = set()
    for override in pricing.get("overrides") or []:
        if (per_mtok(override["prompt"]), per_mtok(override["completion"])) == (peak_in, peak_out):
            if override.get("utc_days") != _WEEKDAYS:
                problems.append(f"peak override on days {override.get('utc_days')}")
            windows.add((override["utc_start"] // 100, override["utc_end"] // 100))
        elif (per_mtok(override["prompt"]), per_mtok(override["completion"])) != (off_in, off_out):
            problems.append(f"an override at neither rate: {override}")
    if windows != set(PEAK_UTC_HOURS):
        problems.append(f"peak windows {sorted(windows)} differ from {sorted(PEAK_UTC_HOURS)}")
    return problems
