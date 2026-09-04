"""Collection management — src/qcagent/retrieval/index.py. Normative
contract: contracts/retrieval.md. Covers T034, T035, T035b, T036b.
"""

import hashlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import httpx
from pydantic import BaseModel
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Modifier,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from qcagent.state import Chunk

COLLECTION = "qdocs"
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"

PAYLOAD_INDEXED_FIELDS = ("library_version", "deprecated", "source")


class CollectionNotFound(Exception):
    """Raised on query against a collection that doesn't exist. The
    collection is never created on demand — ingestion (T031-T035) is a
    distinct, explicit step from querying (contract's error table)."""


class DimensionMismatch(Exception):
    """Raised at initialization, not on the first query, when the embedder's
    `dense_dim` disagrees with what the collection was created with
    (contract's error table)."""


class SnapshotInfo(BaseModel):
    name: str
    local_path: Path
    sha256: str
    point_count: int
    created_at: str


def ensure_collection(client: QdrantClient, dense_dim: int, *, recreate: bool = False) -> None:
    """Creates the `qdocs` collection with two named vectors and the payload
    indexes. Idempotent: no-op if the collection already exists and
    `recreate=False`.

    The IDF modifier on the sparse vector is MANDATORY — see
    embedding.py's `SPARSE_MODEL` docstring: `Qdrant/bm25` emits raw
    term-frequency vectors (`requires_idf=True` on its fastembed model
    card), so without this the sparse branch degenerates to term-count
    matching and loses the rarity weighting that is exactly what lets
    `SparsePauliOp` beat common words in a query.
    """
    exists = client.collection_exists(COLLECTION)
    if exists and not recreate:
        _create_payload_indexes(client)
        return
    if exists and recreate:
        client.delete_collection(COLLECTION)

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config={DENSE_VECTOR: VectorParams(size=dense_dim, distance=Distance.COSINE)},
        sparse_vectors_config={SPARSE_VECTOR: SparseVectorParams(modifier=Modifier.IDF)},
    )
    _create_payload_indexes(client)


def _create_payload_indexes(client: QdrantClient) -> None:
    """Creates a payload index for each field in PAYLOAD_INDEXED_FIELDS.

    CRITICAL (T035): without these, Qdrant can't apply the filter during
    HNSW traversal and falls back to post-filtering. Since obsolete material
    is abundant in this corpus, the pre-filter top-k can be discarded
    entirely and a query that had an answer comes back empty — the failure
    mode that most threatens the M1 gate.

    Idempotent: recreating an existing index is a no-op.
    """
    field_schemas: dict[str, PayloadSchemaType] = {
        "library_version": PayloadSchemaType.KEYWORD,
        "deprecated": PayloadSchemaType.BOOL,
        "source": PayloadSchemaType.KEYWORD,
    }
    for field_name in PAYLOAD_INDEXED_FIELDS:
        client.create_payload_index(
            collection_name=COLLECTION,
            field_name=field_name,
            field_schema=field_schemas[field_name],
        )


def validate_dimensions(client: QdrantClient, dense_dim: int) -> None:
    """Raises `DimensionMismatch` if `dense_dim` disagrees with the
    collection's configured vector size. Callers (e.g. the retriever node's
    constructor) must call this once at initialization — the contract
    explicitly requires the mismatch to surface then, not on the first query,
    since a bad embedder swap should fail loudly before it silently corrupts
    every query in a run.
    """
    if not client.collection_exists(COLLECTION):
        raise CollectionNotFound(f"collection {COLLECTION!r} does not exist")
    info = client.get_collection(COLLECTION)
    vectors_config = info.config.params.vectors
    # `qdocs` is always created with named vectors (ensure_collection above),
    # never the single-unnamed-vector form — the dict branch is the only one
    # a collection built by this module can produce.
    assert isinstance(vectors_config, dict), "qdocs must use named vectors"
    configured = vectors_config[DENSE_VECTOR].size
    if configured != dense_dim:
        raise DimensionMismatch(
            f"embedder dense_dim={dense_dim} does not match collection "
            f"{COLLECTION!r}'s configured size={configured}"
        )


def point_id(doc_id: str) -> str:
    """Deterministic ID so re-ingesting the corpus overwrites instead of
    duplicating (T035b). Never a random UUID or an incrementing counter.
    """
    return str(uuid5(NAMESPACE_URL, doc_id))


def upsert_chunks(
    client: QdrantClient,
    chunks: Sequence[Chunk],
    dense_vectors: Sequence[list[float]],
    sparse_vectors: Sequence[SparseVector],
    *,
    batch_size: int = 256,
    wait: bool = True,
) -> int:
    """Inserts or updates chunks in batches. Returns the number of points
    written.

    `wait=True` by default: ingestion is offline and consistency matters
    more than throughput — the recall evaluation (T041) run right after
    ingestion would get a wrong result against an async write.
    """
    if not (len(chunks) == len(dense_vectors) == len(sparse_vectors)):
        raise ValueError(
            f"length mismatch: chunks={len(chunks)}, dense_vectors={len(dense_vectors)}, "
            f"sparse_vectors={len(sparse_vectors)}"
        )

    points = [
        PointStruct(
            id=point_id(chunk.doc_id),
            vector={DENSE_VECTOR: dense_vec, SPARSE_VECTOR: sparse_vec},
            payload={
                "text": chunk.text,
                "source": chunk.source,
                "library_version": chunk.library_version,
                "deprecated": chunk.deprecated,
                "replacement": chunk.replacement,
                "symbol": chunk.doc_id,
            },
        )
        for chunk, dense_vec, sparse_vec in zip(chunks, dense_vectors, sparse_vectors, strict=True)
    ]

    written = 0
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION, points=batch, wait=wait)
        written += len(batch)
    return written


def snapshot(client: QdrantClient, out_dir: Path) -> SnapshotInfo:
    """Creates a collection snapshot and downloads it to `out_dir`. Returns
    name, local path, and sha256 of the file.

    T036b / Principle II: the returned hash goes into `run_id`. Lets the
    corpus retrievable in week 4 be reconstructed bit-for-bit in week 11,
    even if the upstream documentation has since changed.

    Call at the end of ingestion and before every experimental run.
    """
    description = client.create_snapshot(collection_name=COLLECTION, wait=True)
    if description is None:
        raise RuntimeError("create_snapshot returned no description — snapshot was not created")

    # qdrant-client's generated snapshot API doesn't expose the raw bytes
    # cleanly (SyncSnapshotsApi.get_snapshot returns None on this SDK
    # version); the download endpoint is Qdrant's stable, documented REST
    # route, so fetch it directly instead.
    base_url = client._client.rest_uri  # type: ignore[attr-defined]  # noqa: SLF001 — see comment above
    download_url = f"{base_url}/collections/{COLLECTION}/snapshots/{description.name}"

    out_dir.mkdir(parents=True, exist_ok=True)
    local_path = out_dir / description.name
    with httpx.stream("GET", download_url, timeout=120) as response:
        response.raise_for_status()
        with open(local_path, "wb") as f:
            for chunk in response.iter_bytes():
                f.write(chunk)

    digest = hashlib.sha256(local_path.read_bytes()).hexdigest()
    collection_info = client.get_collection(COLLECTION)

    return SnapshotInfo(
        name=description.name,
        local_path=local_path,
        sha256=digest,
        point_count=collection_info.points_count or 0,
        created_at=datetime.now(UTC).isoformat(),
    )
