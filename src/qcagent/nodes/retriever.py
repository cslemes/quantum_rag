"""retriever node — spec + requirements + retrieval_hint -> chunks (T039).
See plan.md's node contract table (`retriever`: LLM=não) and
contracts/retrieval.md.

Constraint (must survive every future edit to this file): `retry_retrieval`
is the ONLY action that issues a new Qdrant query. `retry_generation` and
`optimize` reuse whatever is already in `state["chunks"]`. If every retry
re-retrieved, conditions C3 (RAG, no loop) and C5 (RAG + loop) would be
indistinguishable on the one axis that matters for H1 — both would show
"retrieval happened every iteration" regardless of which failure drove the
retry, and the ablation this project's central contribution depends on
would have nothing left to measure. This is also already documented as the
graph's design in `routing.py`'s module docstring — this file is what
makes that documented behavior real.
"""

from collections.abc import Callable

from qdrant_client import QdrantClient

from qcagent.retrieval.embedding import Embedder
from qcagent.retrieval.hybrid import RetrievalQuery, search
from qcagent.retrieval.ingest import LIBRARY_VERSION
from qcagent.state import AgentState, CriticDecision, Requirement


def _build_query_text(
    spec: str, requirements: list[Requirement], decision: CriticDecision | None
) -> str:
    parts = [spec]
    if requirements:
        parts.append("; ".join(r.description for r in requirements))
    if decision is not None and decision.retrieval_hint:
        parts.append(decision.retrieval_hint)
    return " — ".join(p for p in parts if p)


def make_retriever_node(
    client: QdrantClient,
    embedder: Embedder,
    *,
    target_version: str = LIBRARY_VERSION,
    limit: int = 8,
) -> Callable[[AgentState], dict]:
    def retriever(state: AgentState) -> dict:
        decision = state.get("decision")
        # No decision yet -> this is the initial retrieval, before the first
        # generation attempt: always a real query. Once a decision exists,
        # only retry_retrieval queries again — see module docstring.
        should_query = decision is None or decision.action == "retry_retrieval"

        if not should_query:
            return {
                "chunks": state.get("chunks", []),
                "trace": [{"node": "retriever", "queried": False}],
            }

        query_text = _build_query_text(
            state.get("spec", ""), state.get("requirements", []), decision
        )
        query = RetrievalQuery(
            text=query_text,
            target_version=target_version,
            limit=limit,
            # include_deprecated left at its default (True): FR-014/D7 —
            # obsolete material must reach the generator LABELED as
            # unusable, never filtered out of the query results themselves.
        )
        chunks = search(client, query, embedder)

        return {
            "chunks": chunks,
            "trace": [
                {
                    "node": "retriever",
                    "queried": True,
                    "query": query_text,
                    "n_chunks": len(chunks),
                    # Which documents, in rank order — what the generator
                    # actually saw (F27).
                    "doc_ids": [c.doc_id for c in chunks],
                }
            ],
        }

    return retriever
