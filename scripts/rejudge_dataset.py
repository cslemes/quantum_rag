"""Judge stored teacher answers again under the current oracle, into a NEW dataset directory.

    python scripts/rejudge_dataset.py --source-dir results/distill/train-v1 \
        --out-dir results/distill/train-v2 --dataset-version train-v2 --admitted 700 \
        --family qft --where inverse=true --where swaps=false \
        --reason "qft inverse/no-SWAP: the oracle was the adjoint, the statement gives R.F^dagger"

Nothing is spent: no teacher call is made, the answers on file are scored again by the same
function the generation run uses (see qcagent/distill/rejudge.py for the rules). The answers of
`--family` that the `--where` filters do NOT select are the control: they must reproduce their
stored verdict, or nothing is written. Needs the sandbox (POSIX): run it in Docker / WSL.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qcagent.config import settings
from qcagent.distill.families import PRODUCTION_FAMILIES
from qcagent.distill.rejudge import RejudgeRefused, rejudge_dataset
from qcagent.validators.sandbox import WorkerPool


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--family", action="append", required=True, help="whose oracle changed")
    parser.add_argument(
        "--where",
        action="append",
        default=[],
        metavar="PARAM=JSON",
        help="re-judge the variations whose parameter equals the value (all filters must hold)",
    )
    parser.add_argument(
        "--admitted",
        type=int,
        required=True,
        help="variations each family was admitted with in the source run (per-family x oversample)",
    )
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    known = {f.name: f for f in PRODUCTION_FAMILIES}
    unknown = [name for name in args.family if name not in known]
    if unknown:
        print(f"unknown families: {unknown}; known: {sorted(known)}", file=sys.stderr)
        return 2
    where = {}
    for item in args.where:
        key, _, value = item.partition("=")
        where[key] = json.loads(value)

    def selects(family, v) -> bool:
        return all(v.params.get(k) == x for k, x in where.items())

    with WorkerPool(
        size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
    ) as pool:
        try:
            summary = rejudge_dataset(
                source_dir=args.source_dir,
                out_dir=args.out_dir,
                families=tuple(known[name] for name in args.family),
                variation_count=args.admitted,
                pool=pool,
                dataset_version=args.dataset_version,
                reason=args.reason,
                selects=selects,
            )
        except RejudgeRefused as exc:
            print(f"refusing: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
