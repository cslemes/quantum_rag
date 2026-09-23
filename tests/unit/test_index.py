"""Contract-required tests for index.py (contracts/retrieval.md's "Testes
exigidos" table): T035's payload indexes and T035b's upsert idempotency.

Both need a REAL Qdrant server — verified directly against `:memory:` mode
during development that it does not actually create payload indexes (logs
"Payload indexes have no effect in the local Qdrant" and returns an empty
`payload_schema`), so these two specific checks cannot be faked against it.
Skipped, not failed, when no server is reachable — consistent with how
GPU-only tests are handled (`pytest.mark.smoke`), just via a live
connectivity check instead of a marker, since this isn't a hardware
dependency.
"""

import httpx
import pytest
from qdrant_client import QdrantClient

from qcagent.retrieval import index as index_module
from qcagent.retrieval.index import COLLECTION, ensure_collection, point_id, upsert_chunks
from qcagent.state import Chunk

# These tests CREATE, RECREATE and DELETE a collection on the live server, so
# they must never touch the one real work depends on. They used to run against
# `COLLECTION` itself: every `pytest` run silently destroyed the ingested index,
# and the next `make eval` measured a system with no retrieval at all. The
# preflight in bench/runner.py now refuses to start in that state, but refusing
# is a second line of defence — the tests should not be doing the damage.
TEST_COLLECTION = "qdocs_test_index"
assert TEST_COLLECTION != COLLECTION

QDRANT_URL = "http://localhost:6333"


def _qdrant_reachable() -> bool:
    try:
        httpx.get(f"{QDRANT_URL}/healthz", timeout=1.0).raise_for_status()
        return True
    except httpx.HTTPError:
        return False


requires_qdrant = pytest.mark.skipif(
    not _qdrant_reachable(), reason=f"requires a live Qdrant server at {QDRANT_URL}"
)

_SAMPLE_CHUNKS = [
    Chunk(
        doc_id="test_index.sample_a",
        text="sample chunk a",
        source="qiskit_api",
        library_version="1.2.4",
        score=0.0,
    ),
    Chunk(
        doc_id="test_index.sample_b",
        text="sample chunk b",
        source="qiskit_api",
        library_version="1.2.4",
        score=0.0,
    ),
]
_DENSE_DIM = 4
_FAKE_DENSE = [[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]]
_FAKE_SPARSE_INDICES = [[1, 2], [3, 4]]


def _fake_sparse_vectors() -> list:
    from qdrant_client.models import SparseVector

    return [SparseVector(indices=idx, values=[1.0] * len(idx)) for idx in _FAKE_SPARSE_INDICES]


@pytest.fixture
def client(monkeypatch):
    """A live client pointed at a THROWAWAY collection.

    `index.py` reads its collection name from a module global, so redirecting
    that global is what makes every function under test operate on the
    disposable name. Both the setup and the teardown then act only on it.
    """
    monkeypatch.setattr(index_module, "COLLECTION", TEST_COLLECTION)
    c = QdrantClient(url=QDRANT_URL)
    if c.collection_exists(TEST_COLLECTION):
        c.delete_collection(TEST_COLLECTION)
    yield c
    if c.collection_exists(TEST_COLLECTION):
        c.delete_collection(TEST_COLLECTION)


@requires_qdrant
def test_payload_indexes_exist_after_ensure_collection(client: QdrantClient) -> None:
    ensure_collection(client, _DENSE_DIM, recreate=True)

    info = client.get_collection(TEST_COLLECTION)

    assert "library_version" in info.payload_schema
    assert "deprecated" in info.payload_schema
    assert "source" in info.payload_schema
    assert info.payload_schema["library_version"].data_type.value == "keyword"
    assert info.payload_schema["deprecated"].data_type.value == "bool"
    assert info.payload_schema["source"].data_type.value == "keyword"


@requires_qdrant
def test_reingesting_the_same_corpus_does_not_change_point_count(client: QdrantClient) -> None:
    ensure_collection(client, _DENSE_DIM, recreate=True)

    upsert_chunks(client, _SAMPLE_CHUNKS, _FAKE_DENSE, _fake_sparse_vectors())
    first_count = client.get_collection(TEST_COLLECTION).points_count

    # Re-ingest the identical corpus — point_id() is deterministic (uuid5 of
    # doc_id), so this must overwrite the same points, not duplicate them.
    upsert_chunks(client, _SAMPLE_CHUNKS, _FAKE_DENSE, _fake_sparse_vectors())
    second_count = client.get_collection(TEST_COLLECTION).points_count

    assert first_count == second_count == len(_SAMPLE_CHUNKS)


def test_point_id_is_deterministic_not_random() -> None:
    assert point_id("QuantumCircuit.cx") == point_id("QuantumCircuit.cx")
    assert point_id("QuantumCircuit.cx") != point_id("QuantumCircuit.h")


def test_upsert_chunks_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        upsert_chunks(
            QdrantClient(":memory:"),
            _SAMPLE_CHUNKS,
            _FAKE_DENSE[:1],  # deliberately short
            _fake_sparse_vectors(),
        )
