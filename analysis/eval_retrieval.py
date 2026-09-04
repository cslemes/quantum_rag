"""M1 gate: recall@8 and MRR over the synthetic query set (T041).

    uv run python -m analysis.eval_retrieval [--queries tests/retrieval/queries.jsonl]
    make eval-retrieval

Gate: recall@8 >= 0.85 (plan.md Milestones). Each line in the query file is
one query with a KNOWN target `doc_id` (matching `Chunk.doc_id`, i.e. the
`symbol` payload field — not the Qdrant point UUID). recall@8 counts a hit
whenever the target appears anywhere in the top-8 results; MRR uses
1/rank of the target's first appearance (0 if absent from the top-8).

An entry MAY also carry `also_correct`: a list of additional doc_ids that
answer the same query just as validly (research.md D17-1). Verified, not
assumed — 25 of the 44 QuantumCircuit-method intent_phrasing queries have a
sibling gate-class chunk whose own docstring explicitly states it's applied
via that exact method (e.g. `CXGate`'s page says "Can be applied to a
QuantumCircuit with the cx() ... method"), so a retriever returning the
class page instead of the method page is not wrong, and counting it as a
miss understates recall. A hit counts if ANY of `target_doc_id` or
`also_correct` appears in the top-k; rank is the best (lowest) among them.
`exact_identifier` entries never carry this — a query that IS the literal
identifier ("QuantumCircuit.cx") asks for that one symbol, not a sibling.
"""

import argparse
import json
import sys
from pathlib import Path

from qdrant_client import QdrantClient

from qcagent.config import settings
from qcagent.retrieval.embedding import Embedder, FastEmbedEmbedder
from qcagent.retrieval.hybrid import RetrievalQuery, search

RECALL_AT_8_GATE = 0.85
DEFAULT_QUERIES_PATH = Path("tests/retrieval/queries.jsonl")


def load_queries(path: Path) -> list[dict]:
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def evaluate(
    client: QdrantClient,
    embedder: Embedder,
    queries: list[dict],
    *,
    target_version: str,
    k: int = 8,
) -> tuple[float, float, list[dict]]:
    """Returns (recall_at_k, mrr, per_query_detail)."""
    hits = 0
    reciprocal_ranks: list[float] = []
    detail: list[dict] = []

    for item in queries:
        query = RetrievalQuery(text=item["query"], target_version=target_version, limit=k)
        results = search(client, query, embedder)
        result_ids = [r.doc_id for r in results]

        acceptable = [item["target_doc_id"], *item.get("also_correct", [])]
        ranks_found = [result_ids.index(t) + 1 for t in acceptable if t in result_ids]
        rank = min(ranks_found) if ranks_found else None

        hit = rank is not None
        hits += int(hit)
        reciprocal_ranks.append(1.0 / rank if rank else 0.0)
        detail.append(
            {
                "query": item["query"],
                "target_doc_id": item["target_doc_id"],
                "also_correct": item.get("also_correct", []),
                "query_type": item.get("query_type", "unlabeled"),
                "rank": rank,
                "top_result": result_ids[0] if result_ids else None,
            }
        )

    recall_at_k = hits / len(queries)
    mrr = sum(reciprocal_ranks) / len(queries)
    return recall_at_k, mrr, detail


def segment_by_query_type(detail: list[dict]) -> dict[str, tuple[float, float, int]]:
    """Per-`query_type` (recall@k, MRR, n) — diagnoses WHICH branch a low
    overall MRR is coming from: exact-identifier queries (e.g. "RZGate")
    lean on the sparse/BM25 branch, intent-phrased ones lean on the dense
    branch. A gap between the two segments' MRR says which branch is
    under-ranking correct-but-not-first hits, which the aggregate MRR alone
    can't show.
    """
    by_type: dict[str, list[dict]] = {}
    for row in detail:
        by_type.setdefault(row["query_type"], []).append(row)

    segments: dict[str, tuple[float, float, int]] = {}
    for query_type, rows in by_type.items():
        hits = sum(1 for r in rows if r["rank"] is not None)
        reciprocal_ranks = [1.0 / r["rank"] if r["rank"] else 0.0 for r in rows]
        segments[query_type] = (hits / len(rows), sum(reciprocal_ranks) / len(rows), len(rows))
    return segments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES_PATH)
    parser.add_argument("--target-version", default="1.2.4")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print every query's rank")
    args = parser.parse_args()

    queries = load_queries(args.queries)
    client = QdrantClient(url=settings.qdrant_url)
    embedder = FastEmbedEmbedder()

    recall_at_8, mrr, detail = evaluate(
        client, embedder, queries, target_version=args.target_version
    )

    if args.verbose:
        for row in detail:
            status = f"rank={row['rank']}" if row["rank"] else "MISS"
            expected = row["target_doc_id"]
            if row["also_correct"]:
                expected = f"{expected!r} (also accepted: {row['also_correct']!r})"
            else:
                expected = repr(expected)
            print(f"  [{status:>8}] {row['query']!r} -> expected {expected}")
            if row["rank"] is None:
                print(f"             top result was {row['top_result']!r}")

    print(f"\nqueries: {len(queries)}")
    print(f"recall@8: {recall_at_8:.4f}")
    print(f"MRR: {mrr:.4f}")

    print("\nper query_type:")
    for query_type, (seg_recall, seg_mrr, n) in sorted(segment_by_query_type(detail).items()):
        print(f"  {query_type:<18} n={n:<3} recall@8={seg_recall:.4f}  MRR={seg_mrr:.4f}")

    gate_verdict = "PASS" if recall_at_8 >= RECALL_AT_8_GATE else "FAIL"
    print(f"\nM1 gate (recall@8 >= {RECALL_AT_8_GATE}): {gate_verdict}")

    if recall_at_8 < RECALL_AT_8_GATE:
        sys.exit(1)


if __name__ == "__main__":
    main()
