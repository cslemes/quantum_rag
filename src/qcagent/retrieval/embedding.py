"""Embedder implementation. See contracts/retrieval.md's `Embedder` Protocol.

Dense model choice (D4, research.md) is PENDENTE-PILOTO: recall@8 (T041)
decides between a code-specific and a general multilingual candidate.
`FastEmbedEmbedder` takes either as a constructor argument so the pilot can
swap models without touching any caller.
"""

import os
from collections.abc import Sequence
from pathlib import Path
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

# research.md D18/D18b — the exact HuggingFace snapshot (commit) of every model
# the system loads. fastembed 0.3.6 cannot pin a revision itself, so the
# pinning lives here: `scripts/fetch_models.py` downloads exactly these
# commits into the pinned cache, and every load checks the cache holds exactly
# these commits before touching fastembed. A model not listed here cannot be
# loaded — adding one (e.g. the D4 multilingual candidate) is a deliberate
# edit, not something a first `import` does over the network.
PINNED_MODEL_REVISIONS: dict[str, str] = {
    DENSE_MODEL_CODE: "516f4baf13dec4ddddda8631e019b5737c8bc250",
    SPARSE_MODEL: "22b8d2af71a76161e18dd432d2cee0eefa66e412",
}

# Outside the canonical image, the pinned cache lives under the user's cache
# directory, filled once by `make models`. Inside the image,
# FASTEMBED_CACHE_PATH points at the copy baked in at build time. Never
# fastembed's own default, `/tmp/fastembed_cache`, which does not survive and
# was where the suite's intermittent downloads came from.
#
# Deliberately NOT inside the repository: HuggingFace's cache links each file
# in `snapshots/<commit>/` to a file in `blobs/`, and the repo is mounted from
# the host over virtiofs, where `ln -s` reports success and creates nothing.
# A `make models` run there downloaded every blob and left the snapshot
# directory empty, which the preflight below then correctly refused.
DEFAULT_MODEL_CACHE = (
    Path(os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache"))
    / "qcircuit-agent"
    / "fastembed"
)


def _model_files(model_name: str) -> list[str]:
    """The files fastembed opens for `model_name`, from its own model
    description (`model_file` plus `additional_files`)."""
    for m in TextEmbedding.list_supported_models() + SparseTextEmbedding.list_supported_models():
        if m["model"] == model_name:
            # `Qdrant/bm25` declares `model_file: "mock.file"` — fastembed's own
            # placeholder ("bm25 does not require a model, so we just use a
            # mock", fastembed/sparse/bm25.py). No such file exists upstream and
            # nothing opens it; only the stopword lists are real.
            model_file = [] if m["model_file"] == "mock.file" else [m["model_file"]]
            return [*model_file, *m.get("additional_files", [])]
    raise KeyError(f"{model_name} is not a model fastembed supports")


class ModelNotCachedError(RuntimeError):
    """A pinned model is missing from the pinned cache, or the cache holds a
    different revision. Raised BEFORE fastembed is called: fastembed's own
    missing-model path sleeps through retries and then reports only "could
    not download model", which is how a missing or stale cache turned into
    a 99-second run with errors nobody could name."""


def model_cache_dir(cache_dir: str | Path | None = None) -> Path:
    if cache_dir is not None:
        return Path(cache_dir)
    return Path(os.environ.get("FASTEMBED_CACHE_PATH") or DEFAULT_MODEL_CACHE)


def require_pinned_model(model_name: str, cache_dir: Path) -> None:
    """Fails fast, with the fix, unless `cache_dir` holds exactly the pinned
    revision of `model_name`. Reads HuggingFace's cache layout directly
    (`models--org--name/refs/main` -> `snapshots/<commit>/`) — no network,
    no fastembed, no retries."""
    fix = "run `make models` (or rebuild the image) to populate the pinned cache"
    pinned = PINNED_MODEL_REVISIONS.get(model_name)
    if pinned is None:
        raise ModelNotCachedError(
            f"{model_name!r} has no pinned revision in PINNED_MODEL_REVISIONS — "
            "add one deliberately before loading this model"
        )
    repo_dir = cache_dir / f"models--{model_name.replace('/', '--')}"
    ref = repo_dir / "refs" / "main"
    if not ref.is_file():
        raise ModelNotCachedError(f"{model_name} is not in the model cache at {cache_dir}; {fix}")
    cached = ref.read_text().strip()
    if cached != pinned:
        raise ModelNotCachedError(
            f"{model_name} in {cache_dir} is revision {cached}, but {pinned} is pinned; {fix}"
        )
    snapshot = repo_dir / "snapshots" / pinned
    # Every file fastembed will open must exist, not just the directory: a
    # snapshot whose links didn't survive a copy (HuggingFace's cache is built
    # from symlinks, and the repo's host mount doesn't support them) passed a
    # directory-only check and then failed deep inside onnxruntime with
    # "NO_SUCHFILE" — the exact unnamed failure this check exists to prevent.
    missing = [
        name
        for name in _model_files(model_name)
        if not (snapshot / name).is_file() or (snapshot / name).stat().st_size == 0
    ]
    if missing:
        raise ModelNotCachedError(
            f"{model_name} revision {pinned} in {cache_dir} is incomplete — missing or "
            f"empty: {missing}; {fix}"
        )


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
        cache_dir: str | Path | None = None,
    ) -> None:
        # Models load ONLY from the pinned cache, never over the network:
        # `local_files_only=True` is forwarded by fastembed down to
        # `huggingface_hub.snapshot_download`, and both pinned models are
        # HuggingFace-only (no fallback URL). Without it, fastembed contacted
        # the Hub on EVERY construction even with the model already cached.
        # Downloading is `scripts/fetch_models.py`'s job alone.
        resolved_cache = model_cache_dir(cache_dir)
        require_pinned_model(dense_model_name, resolved_cache)
        require_pinned_model(sparse_model_name, resolved_cache)
        # `threads` bounds ONNX Runtime's intra-op parallelism. Left at its
        # own default, a full-corpus ingestion (995 chunks) was observed
        # accumulating 135 CPU-minutes across ~14 wall-clock minutes on this
        # machine — many more threads than cores helping — while RSS sat at
        # ~13 GB of 15 GB, one bad batch away from the OOM kill this was
        # already fixed once for. Capping threads reduces peak memory (fewer
        # concurrent per-thread buffers) without slowing single-batch work
        # past what the CPU can actually do in parallel anyway.
        self._dense = TextEmbedding(
            model_name=dense_model_name,
            cache_dir=str(resolved_cache),
            threads=threads,
            local_files_only=True,
        )
        self._sparse = SparseTextEmbedding(
            model_name=sparse_model_name,
            cache_dir=str(resolved_cache),
            threads=threads,
            local_files_only=True,
        )
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
