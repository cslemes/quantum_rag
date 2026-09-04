"""Embedder implementation. See contracts/retrieval.md's `Embedder` Protocol.

Dense model choice (D4, research.md) is PENDENTE-PILOTO: recall@8 (T041)
decides between a code-specific and a general multilingual candidate.
`FastEmbedEmbedder` takes either as a constructor argument so the pilot can
swap models without touching any caller.
"""

from collections.abc import Sequence
from typing import Protocol

from fastembed import SparseTextEmbedding, TextEmbedding
from qdrant_client.models import SparseVector

# D4 candidates — corpus is majority English code/docstring (favors the code
# model), but task descriptions may arrive in Portuguese (favors multilingual).
# Confirmed empirically only via T041's recall@8 pilot.
DENSE_MODEL_CODE = "jinaai/jina-embeddings-v2-base-code"
DENSE_MODEL_MULTILINGUAL = "intfloat/multilingual-e5-large"
DEFAULT_DENSE_MODEL = DENSE_MODEL_CODE

# D5 — BM25 via fastembed. `Qdrant/bm25`'s model card declares
# `requires_idf=True` (confirmed against the installed fastembed==0.3.6): the
# vectors it emits are raw term-frequency, not IDF-weighted. The
# `Modifier.IDF` in index.py's `SparseVectorParams` is therefore mandatory,
# not optional — resolves the "decide and record" note in
# contracts/retrieval.md's `ensure_collection` docstring.
SPARSE_MODEL = "Qdrant/bm25"

_SUPPORTED_DENSE_DIMS: dict[str, int] = {
    m["model"]: m["dim"] for m in TextEmbedding.list_supported_models()
}


class Embedder(Protocol):
    """Matches contracts/retrieval.md exactly. Document and query methods are
    kept separate on purpose (the contract's "assimetria proposital") — some
    models need different prefixes for the two roles, and using the wrong one
    degrades recall silently.
    """

    @property
    def dense_dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def embed_sparse_documents(self, texts: Sequence[str]) -> list[SparseVector]: ...
    def embed_sparse_query(self, text: str) -> SparseVector: ...


class FastEmbedEmbedder:
    """Concrete `Embedder` backed by `fastembed`. The document/query asymmetry
    is handled internally by `TextEmbedding.embed()` vs `.query_embed()` and
    `SparseTextEmbedding.embed()` vs `.query_embed()` — fastembed applies the
    model-specific prefix itself; this class never touches prefix strings.
    """

    def __init__(
        self,
        dense_model_name: str = DEFAULT_DENSE_MODEL,
        sparse_model_name: str = SPARSE_MODEL,
        *,
        batch_size: int = 8,
        threads: int = 4,
    ) -> None:
        # `threads` bounds ONNX Runtime's intra-op parallelism. Left at its
        # own default, a full-corpus ingestion (995 chunks) was observed
        # accumulating 135 CPU-minutes across ~14 wall-clock minutes on this
        # machine — many more threads than cores helping — while RSS sat at
        # ~13 GB of 15 GB, one bad batch away from the OOM kill this was
        # already fixed once for. Capping threads reduces peak memory (fewer
        # concurrent per-thread buffers) without slowing single-batch work
        # past what the CPU can actually do in parallel anyway.
        self._dense = TextEmbedding(model_name=dense_model_name, threads=threads)
        self._sparse = SparseTextEmbedding(model_name=sparse_model_name, threads=threads)
        self._dense_dim = _SUPPORTED_DENSE_DIMS[dense_model_name]
        # fastembed's own default (256) puts every document in one ONNX
        # batch, padded to the longest sequence in it — on a real corpus
        # with a handful of long chunks mixed into hundreds of short ones,
        # that padding blew attention memory up past what the ONNX runtime
        # would allocate (a 6.7k-char chunk was enough to trigger it against
        # 186 documents in a single batch). A small fixed batch size bounds
        # the padding waste per batch instead.
        self._batch_size = batch_size

    @property
    def dense_dim(self) -> int:
        return self._dense_dim

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [vec.tolist() for vec in self._dense.embed(list(texts), batch_size=self._batch_size)]

    def embed_query(self, text: str) -> list[float]:
        vec = next(iter(self._dense.query_embed([text])))
        return [float(x) for x in vec]

    def embed_sparse_documents(self, texts: Sequence[str]) -> list[SparseVector]:
        return [
            SparseVector(indices=emb.indices.tolist(), values=emb.values.tolist())
            for emb in self._sparse.embed(list(texts), batch_size=self._batch_size)
        ]

    def embed_sparse_query(self, text: str) -> SparseVector:
        emb = next(iter(self._sparse.query_embed([text])))
        return SparseVector(indices=emb.indices.tolist(), values=emb.values.tolist())
