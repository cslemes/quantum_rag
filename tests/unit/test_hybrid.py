"""Contract-required tests for hybrid.py (contracts/retrieval.md's "Testes
exigidos" table): version filtering, the RZGate/RXGate sparse-retrieval
critical case (T040b), deprecated-chunk prompt marking (FR-014), and
register splitting (FR-015).

The critical-case test (`:memory:` Qdrant) is real, not mocked: it embeds
two genuine chunks with the actual configured embedder and runs the actual
hybrid search — verified during development that `:memory:` mode executes
the same prefetch+fusion query path as a live server (unlike payload
indexes, which it silently no-ops — see test_index.py).
"""

from qdrant_client import QdrantClient
from qdrant_client.models import MatchValue

from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.retrieval.hybrid import (
    RetrievalBundle,
    RetrievalQuery,
    build_filter,
    search,
    split_by_register,
)
from qcagent.retrieval.index import ensure_collection, upsert_chunks
from qcagent.state import Chunk


def test_build_filter_excludes_the_wrong_version() -> None:
    query = RetrievalQuery(text="cx", target_version="1.2.4")

    condition = build_filter(query)

    assert len(condition.must) == 1
    field = condition.must[0]
    assert field.key == "library_version"
    assert isinstance(field.match, MatchValue)
    assert field.match.value == "1.2.4"


def test_build_filter_excludes_deprecated_when_asked() -> None:
    query = RetrievalQuery(text="execute", target_version="1.2.4", include_deprecated=False)

    condition = build_filter(query)

    assert condition.must_not is not None
    assert condition.must_not[0].key == "deprecated"
    assert condition.must_not[0].match.value is True


def test_build_filter_default_includes_deprecated() -> None:
    """FR-014's default: obsolete material reaches the generator labeled as
    unusable, not filtered out. must_not stays empty unless the caller
    explicitly opts into excluding it (the ablation arm)."""
    query = RetrievalQuery(text="execute", target_version="1.2.4")

    condition = build_filter(query)

    assert not condition.must_not


def _embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder()


def _seed_rz_rx_corpus(client: QdrantClient, embedder: FastEmbedEmbedder) -> None:
    chunks = [
        Chunk(
            doc_id="RZGate",
            text="RZGate applies a single-qubit rotation about the Z axis.",
            source="qiskit_api",
            library_version="1.2.4",
            score=0.0,
        ),
        Chunk(
            doc_id="RXGate",
            text="RXGate applies a single-qubit rotation about the X axis.",
            source="qiskit_api",
            library_version="1.2.4",
            score=0.0,
        ),
    ]
    ensure_collection(client, embedder.dense_dim)
    dense = embedder.embed_documents([c.text for c in chunks])
    sparse = embedder.embed_sparse_documents([c.text for c in chunks])
    upsert_chunks(client, chunks, dense, sparse)


def test_rzgate_query_ranks_rzgate_above_rxgate() -> None:
    """The case that justifies the hybrid index existing at all (D5): a
    query naming `RZGate` explicitly must rank the `RZGate` chunk above
    `RXGate` — dense embedding alone tends to conflate the two since they
    differ by one character and describe near-identical operations; the
    sparse (BM25) branch is what should break the tie correctly."""
    client = QdrantClient(":memory:")
    embedder = _embedder()
    _seed_rz_rx_corpus(client, embedder)

    query = RetrievalQuery(
        text="How do I use RZGate in my circuit?", target_version="1.2.4", limit=8
    )
    results = search(client, query, embedder)

    doc_ids = [r.doc_id for r in results]
    assert "RZGate" in doc_ids
    assert "RXGate" in doc_ids
    assert doc_ids.index("RZGate") < doc_ids.index("RXGate")


def test_to_prompt_context_marks_deprecated_chunk_with_replacement() -> None:
    bundle = RetrievalBundle(
        api_chunks=[
            Chunk(
                doc_id="execute",
                text="Runs a circuit on a backend.",
                source="qiskit_api",
                library_version="1.2.4",
                deprecated=True,
                replacement="backend.run() / Sampler / Estimator",
                score=0.9,
            ),
            Chunk(
                doc_id="QuantumCircuit.cx",
                text="Applies CXGate.",
                source="qiskit_api",
                library_version="1.2.4",
                score=0.8,
            ),
        ],
        paper_chunks=[],
    )

    rendered = bundle.to_prompt_context()

    assert "[OBSOLETO — NÃO USAR] execute" in rendered
    assert "Substituir por: backend.run() / Sampler / Estimator" in rendered
    # The current chunk must NOT carry the obsolete marker.
    assert "[OBSOLETO — NÃO USAR] QuantumCircuit.cx" not in rendered


def test_split_by_register_separates_arxiv_from_api_docs() -> None:
    api_chunk = Chunk(
        doc_id="QuantumCircuit.h",
        text="Applies HGate.",
        source="qiskit_api",
        library_version="1.2.4",
        score=0.5,
    )
    paper_chunk = Chunk(
        doc_id="arxiv:1234.5678",
        text="We propose a variational algorithm...",
        source="arxiv",
        library_version=None,
        score=0.5,
    )

    bundle = split_by_register([api_chunk, paper_chunk])

    assert bundle.api_chunks == [api_chunk]
    assert bundle.paper_chunks == [paper_chunk]
