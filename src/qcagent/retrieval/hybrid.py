"""Hybrid search — src/qcagent/retrieval/hybrid.py. Normative contract:
contracts/retrieval.md. Covers T036, T036b(snapshot lives in index.py),
T037, T038.
"""

from collections.abc import Sequence

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.http.models import Condition
from qdrant_client.models import (
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchAny,
    MatchValue,
    Prefetch,
)

from qcagent.retrieval.embedding import Embedder
from qcagent.retrieval.index import COLLECTION, DENSE_VECTOR, SPARSE_VECTOR, CollectionNotFound
from qcagent.state import Chunk


class RetrievalQuery(BaseModel):
    """Entry for one query. Built by the retriever node."""

    text: str
    target_version: str  # e.g. "1.2.4" — FR-011
    sources: list[str] | None = None  # None = all sources
    include_deprecated: bool = True  # FR-014: label, don't omit
    limit: int = 8
    prefetch_limit: int = 40  # candidates per branch before fusion


def build_filter(query: RetrievalQuery) -> Filter:
    """Builds the Qdrant filter from a query.

      must:     library_version == query.target_version
                source IN query.sources          (if not None)
      must_not: deprecated == True                (if include_deprecated=False)

    FR-014: the default is include_deprecated=True. Obsolete material MUST
    reach the generator labeled as unusable, not be filtered out (D7,
    research.md). The parameter exists for the ablation arm and for
    isolated retriever evaluation, not for the normal path.
    """
    must: list[Condition] = [
        FieldCondition(key="library_version", match=MatchValue(value=query.target_version))
    ]
    if query.sources is not None:
        must.append(FieldCondition(key="source", match=MatchAny(any=query.sources)))
    must_not: list[Condition] = []
    if not query.include_deprecated:
        must_not.append(FieldCondition(key="deprecated", match=MatchValue(value=True)))
    return Filter(must=must, must_not=must_not or None)


def search(client: QdrantClient, query: RetrievalQuery, embedder: Embedder) -> list[Chunk]:
    """Hybrid query in a SINGLE round-trip via the Query API.

    The filter goes on EACH branch of the prefetch, not just at the outer
    level — filtering after fusion wastes candidates and reintroduces the
    post-filtering problem T035's payload indexes exist to avoid.

    Returns Chunks ordered by descending score, with `deprecated` and
    `replacement` populated from the payload.
    """
    if not client.collection_exists(COLLECTION):
        raise CollectionNotFound(
            f"collection {COLLECTION!r} does not exist — ingest before querying, "
            "it is never created on demand"
        )

    condition = build_filter(query)
    prefetch = [
        Prefetch(
            query=embedder.embed_query(query.text),
            using=DENSE_VECTOR,
            limit=query.prefetch_limit,
            filter=condition,
        ),
        Prefetch(
            query=embedder.embed_sparse_query(query.text),
            using=SPARSE_VECTOR,
            limit=query.prefetch_limit,
            filter=condition,
        ),
    ]
    response = client.query_points(
        collection_name=COLLECTION,
        prefetch=prefetch,
        query=FusionQuery(fusion=Fusion.RRF),
        limit=query.limit,
        with_payload=True,
    )
    chunks = []
    for point in response.points:
        assert point.payload is not None, "with_payload=True but point has no payload"
        chunks.append(
            Chunk(
                # payload["symbol"] is the original doc_id (data-model.md's
                # payload mapping) — point.id is the deterministic uuid5
                # derived FROM it (index.py's point_id), not usable to match
                # against a query's known-target doc_id.
                doc_id=point.payload["symbol"],
                text=point.payload["text"],
                source=point.payload["source"],
                library_version=point.payload.get("library_version"),
                deprecated=point.payload.get("deprecated", False),
                replacement=point.payload.get("replacement"),
                score=point.score,
            )
        )
    return chunks


_API_SOURCES = {"qiskit_api", "pennylane_api", "migration_guide"}


class RetrievalBundle(BaseModel):
    api_chunks: list[Chunk]
    paper_chunks: list[Chunk]

    def to_prompt_context(self) -> str:
        """Renders the RAG context block for the generator's prompt.

        Format contract (contracts/retrieval.md):
          - API block first, paper block second, each with a header.
          - A chunk with deprecated=True is rendered with an explicit
            prohibition marker and its `replacement` field visible — the
            contrast is the mechanism (D7): omitting obsolete material
            doesn't undo what the model memorized in training; declaring the
            prohibition actively corrects it.
          - A current chunk is rendered without any marking.
        """
        lines: list[str] = []
        if self.api_chunks:
            lines.append("## API reference")
            for chunk in self.api_chunks:
                lines.append(_render_chunk(chunk))
        if self.paper_chunks:
            lines.append("## Algorithm references")
            for chunk in self.paper_chunks:
                lines.append(_render_chunk(chunk))
        return "\n\n".join(lines)


def _render_chunk(chunk: Chunk) -> str:
    if chunk.deprecated:
        header = f"[OBSOLETO — NÃO USAR] {chunk.doc_id}\nSubstituir por: {chunk.replacement}"
        return f"{header}\n{chunk.text}"
    return chunk.text


def split_by_register(chunks: Sequence[Chunk]) -> RetrievalBundle:
    """FR-015: separates API reference material from descriptive algorithm
    material — the two registers answer different questions and must reach
    the generator in distinguishable blocks.
    """
    api_chunks = [c for c in chunks if c.source in _API_SOURCES]
    paper_chunks = [c for c in chunks if c.source == "arxiv"]
    return RetrievalBundle(api_chunks=api_chunks, paper_chunks=paper_chunks)
