"""Export the accepted teacher records as `train.jsonl`, with the student's planner and retriever.

    python scripts/export_training_set.py --records-dir results/distill/<version> \
        --out data/train.jsonl --profile local-1.5b-rp --per-family 350

Needs the live student stack, exactly as the benchmark does: Ollama serving the profile at the
version the profile pins (refused otherwise, no fallback), and Qdrant with the ingested index.
The server's state is reset before every planner call, as the suite does per run, so a planner
output does not depend on what was asked before it. Writes `train.jsonl` and `train.meta.json`
(see qcagent/distill/export.py for what the meta records). Nothing is spent: the planner is the
local student; no teacher call is made here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from bench.run_single import gate_profile
from qcagent.config import settings
from qcagent.distill.export import ExportRefused, export_dataset
from qcagent.distill.families import PRODUCTION_FAMILIES
from qcagent.distill.gate import StatementRegistry
from qcagent.live import MAX_QUBITS
from qcagent.llm.profiles import build_client, reset_server_state
from qcagent.nodes.planner import make_planner_node
from qcagent.nodes.retriever import make_retriever_node
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.retrieval.index import COLLECTION
from qcagent.retrieval.ingest import LIBRARY_VERSION

SEED = 1  # the suite's first seed; the planner is asked at temperature 0 either way


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--profile", required=True, help="the STUDENT's generator profile")
    parser.add_argument("--per-family", type=int, default=None)
    args = parser.parse_args()

    profile, status = gate_profile(args.profile)  # ProfileError: unreachable or wrong build
    llm = build_client(profile)
    qdrant = QdrantClient(url=settings.qdrant_url)
    embedder = FastEmbedEmbedder()
    planner = make_planner_node(llm, max_qubits=MAX_QUBITS, seed=SEED)
    retriever = make_retriever_node(qdrant, embedder)

    def reset_then_plan(state: dict) -> dict:
        reset_server_state(profile)
        return planner(state)

    info = qdrant.get_collection(COLLECTION)
    environment = {
        "student_profile": profile.name,
        "student_model": profile.model,
        "student_model_digest": status.model_digest,
        "server_version": status.server_version,
        "expected_server_version": profile.expected_server_version,
        "determinism": profile.determinism.model_dump(mode="json"),
        "planner_seed": SEED,
        "qdrant_collection": COLLECTION,
        "qdrant_points": info.points_count,
        "library_version": LIBRARY_VERSION,
        "embedder": type(embedder).__name__,
    }
    try:
        report = export_dataset(
            registry=StatementRegistry(args.records_dir / "registry.jsonl"),
            records_path=args.records_dir / "records.jsonl",
            meta_path=args.records_dir / "dataset_meta.json",
            out_path=args.out,
            planner=reset_then_plan,
            retriever=retriever,
            environment=environment,
            family_order=[f.name for f in PRODUCTION_FAMILIES],
            per_family=args.per_family,
        )
    except ExportRefused as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {k: report[k] for k in ("rows", "per_family", "skipped", "file_sha256")}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
