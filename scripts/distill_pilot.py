"""Run the distillation pilot: 4 families x 20 statements, one teacher, one sample each.

    python scripts/distill_pilot.py --out-dir results/distill/pilot-v1 --dataset-version pilot-v1

Refuses to start unless OPENROUTER_API_KEY is set (in the environment or .env). It
reads the key only to hand it to the HTTP client; it is never printed or written.
Stops, and reports, if actual spend passes 3x the registered estimate.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from qcagent.config import settings
from qcagent.distill.families import PILOT_FAMILIES
from qcagent.distill.gate import StatementRegistry
from qcagent.distill.listing import listing_entry, snapshot_facts
from qcagent.distill.pilot import run_pilot
from qcagent.distill.spend import SpendGuard, estimate_from_tokens
from qcagent.llm.profiles import build_client, get_profile
from qcagent.validators.sandbox import WorkerPool

PROFILE = "teacher-deepseek-v4.1-flash-1017"
#: operator-registered estimate for the 80-statement pilot (2026-10-24)
REGISTERED_ESTIMATE_USD = 0.12
#: the assumed size of one call, for the labelled start-time estimate only
ASSUMED_INPUT_TOKENS, ASSUMED_OUTPUT_TOKENS = 900, 2100


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args()

    profile = get_profile(PROFILE)
    client = build_client(profile)  # ProfileError, without the value, if the key is absent
    facts = snapshot_facts(listing_entry(profile.model))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    registry = StatementRegistry(args.out_dir / "registry.jsonl")
    for family in PILOT_FAMILIES:
        registry.admit_family(family)  # BuilderDisagreement stops here, before any spend

    n_statements = sum(1 for e in registry.entries() if e["verdict"] == "pass")
    estimate = estimate_from_tokens(
        n_statements,
        ASSUMED_INPUT_TOKENS,
        ASSUMED_OUTPUT_TOKENS,
        now=datetime.now(UTC),
    )
    guard = SpendGuard(estimate_usd=REGISTERED_ESTIMATE_USD)
    print(
        f"{n_statements} statements; labelled estimate ${estimate.usd} ({estimate.window}); "
        f"registered estimate ${REGISTERED_ESTIMATE_USD}, stop above ${guard.ceiling_usd:.2f}",
        file=sys.stderr,
    )
    with WorkerPool(
        size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
    ) as pool:
        summary = run_pilot(
            registry=registry,
            families=PILOT_FAMILIES,
            client=client,
            profile=profile,
            out_dir=args.out_dir,
            guard=guard,
            estimate=estimate,
            dataset_version=args.dataset_version,
            pool=pool,
            snapshot=facts,
        )
    print(json.dumps(summary["spend"], indent=2))
    print(f"outcomes: {summary['outcomes']}; halted: {summary['halted']}", file=sys.stderr)
    return 1 if summary["halted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
