"""Run the distillation pilot: 4 families x 20 statements, one teacher, one sample each.

    python scripts/distill_pilot.py --out-dir results/distill/pilot-v1 --dataset-version pilot-v1

Refuses to start unless it is told, in so many words, to spend: `--authorize-spend USD`
(the most it may spend; it must be at least the 3x stop ceiling). A credential being
present is NOT permission: the flag is checked before the credential is even looked
up. Then, before any real call, the NEGATIVE CONTROL runs against the real pipeline
over a local transport and the run proceeds only if it fired (wrong circuits
rejected with reason codes, correct ones accepted). The key is read only to hand it
to the HTTP client; it is never printed or written. Stops, and reports, if actual
spend passes 3x the registered estimate.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from qcagent.config import settings
from qcagent.distill.control import run_negative_control
from qcagent.distill.families import PILOT_FAMILIES
from qcagent.distill.gate import StatementRegistry
from qcagent.distill.listing import listing_entry, snapshot_facts
from qcagent.distill.pilot import SpendAuthorization, run_pilot
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
    parser.add_argument(
        "--authorize-spend",
        type=float,
        default=None,
        metavar="USD",
        help="explicit permission to spend up to USD; without it nothing is spent",
    )
    args = parser.parse_args()

    # 1. The positive gate, before anything that could spend or even look for a key.
    guard = SpendGuard(estimate_usd=REGISTERED_ESTIMATE_USD)
    if args.authorize_spend is None:
        print(
            "refusing: no --authorize-spend given (a credential is not permission)", file=sys.stderr
        )
        return 2
    if args.authorize_spend < guard.ceiling_usd:
        print(
            f"refusing: --authorize-spend {args.authorize_spend} is below the stop ceiling "
            f"${guard.ceiling_usd:.2f}",
            file=sys.stderr,
        )
        return 2
    authorization = SpendAuthorization(
        ceiling_usd=args.authorize_spend,
        granted_by=f"operator, via --authorize-spend {args.authorize_spend}",
    )

    # The sandbox workers are forked from this process, so the pool is created
    # FIRST. Verified on 2026-10-24: once the parent has run the Pauli-energy
    # family's builder A (SparsePauliOp.to_matrix and eigvalsh), a worker forked
    # afterwards hangs on the same call in generated code (the first live run lost
    # ten energy statements to 60 s sandbox timeouts). Single-thread environment
    # variables (BLAS, Rayon, QISKIT_PARALLEL) did not help; forking first did.
    with WorkerPool(
        size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
    ) as pool:
        return _run(args, guard, authorization, pool)


def _run(args, guard: SpendGuard, authorization: SpendAuthorization, pool: WorkerPool) -> int:
    profile = get_profile(PROFILE)
    facts = snapshot_facts(listing_entry(profile.model))  # public listing; no credential
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # 2. The negative control, on the real pipeline, with no network and no spend.
    control_dir = args.out_dir / "negative_control"
    shutil.rmtree(control_dir, ignore_errors=True)  # our own output, rebuilt each time
    control = run_negative_control(
        families=PILOT_FAMILIES, profile=profile, snapshot=facts, pool=pool, work_dir=control_dir
    )
    (args.out_dir / "negative_control.json").write_text(json.dumps(control, indent=2) + "\n")
    print(
        f"negative control: fired={control['fired']}, wrong rejected "
        f"{control['wrong_rejected']}, correct accepted {control['correct_accepted']}",
        file=sys.stderr,
    )
    if not control["fired"]:
        print("refusing: the negative control did not fire; nothing was spent", file=sys.stderr)
        return 3

    client = build_client(profile)  # ProfileError, without the value, if the key is absent
    registry = StatementRegistry(args.out_dir / "registry.jsonl")
    for family in PILOT_FAMILIES:
        registry.admit_family(family)  # BuilderDisagreement stops here, before any spend

    n_statements = sum(1 for e in registry.entries() if e["verdict"] == "pass")
    estimate = estimate_from_tokens(
        n_statements, ASSUMED_INPUT_TOKENS, ASSUMED_OUTPUT_TOKENS, now=datetime.now(UTC)
    )
    print(
        f"{n_statements} statements; labelled estimate ${estimate.usd} ({estimate.window}); "
        f"registered estimate ${REGISTERED_ESTIMATE_USD}, stop above ${guard.ceiling_usd:.2f}",
        file=sys.stderr,
    )
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
        authorization=authorization,
    )
    print(json.dumps(summary["spend"], indent=2))
    print(f"outcomes: {summary['outcomes']}; halted: {summary['halted']}", file=sys.stderr)
    return 1 if summary["halted"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
