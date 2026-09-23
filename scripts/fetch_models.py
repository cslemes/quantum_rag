"""Populate the pinned model cache — the ONLY code in this project that
downloads model weights (research.md D18b).

    uv run python scripts/fetch_models.py [cache_dir]      # or: make models

Downloads exactly the commits in `PINNED_MODEL_REVISIONS` into the cache
(default: FASTEMBED_CACHE_PATH, else the repo's `.cache/fastembed`), using the
same file patterns fastembed itself requests, then proves the result loads
with the network unused (`FastEmbedEmbedder` loads with
`local_files_only=True`). Run once per machine, or at image build time;
everything else — ingestion, the agent, the test suite — only ever reads it.

Idempotent: a model already present at its pinned revision is not fetched
again.
"""

import sys
from pathlib import Path

from fastembed import SparseTextEmbedding, TextEmbedding
from huggingface_hub import snapshot_download

from qcagent.retrieval.embedding import (
    PINNED_MODEL_REVISIONS,
    FastEmbedEmbedder,
    ModelNotCachedError,
    model_cache_dir,
    require_pinned_model,
)

# fastembed's own base patterns (fastembed/common/model_management.py,
# download_files_from_huggingface); the model file and additional files come
# from each model's description below.
_BASE_PATTERNS = [
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "preprocessor_config.json",
]


def _description(model_name: str) -> dict:
    for m in TextEmbedding.list_supported_models() + SparseTextEmbedding.list_supported_models():
        if m["model"] == model_name:
            return m
    raise SystemExit(f"{model_name} is not a model fastembed supports")


def require_symlink_support(cache_dir: Path) -> None:
    """HuggingFace's cache layout is built from symlinks (`snapshots/<commit>/
    file -> ../../blobs/<hash>`). Some mounts — notably the virtiofs host
    mount this repo lives on — accept `symlink()` without creating anything,
    so a download "succeeds" while leaving every snapshot directory empty.
    Refuse that up front instead of downloading 640 MB into an unusable
    layout."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target, link = cache_dir / ".symlink-probe", cache_dir / ".symlink-probe.link"
    try:
        target.write_text("probe")
        link.unlink(missing_ok=True)
        try:
            link.symlink_to(target.name)
            usable = link.is_symlink() and link.exists()
        except OSError:
            usable = False
        if not usable:
            raise SystemExit(
                f"{cache_dir} is on a filesystem that cannot hold symlinks, which the "
                "HuggingFace cache layout requires. Set FASTEMBED_CACHE_PATH to a path "
                "on a local filesystem (the default is under your XDG cache directory)."
            )
    finally:
        link.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def fetch(model_name: str, revision: str, cache_dir: Path) -> None:
    try:
        require_pinned_model(model_name, cache_dir)
        print(f"  {model_name}@{revision[:12]} already cached")
        return
    except ModelNotCachedError:
        pass

    desc = _description(model_name)
    patterns = [*_BASE_PATTERNS, desc["model_file"], *desc.get("additional_files", [])]
    snapshot_download(
        repo_id=desc["sources"]["hf"],
        revision=revision,
        allow_patterns=patterns,
        cache_dir=str(cache_dir),
    )
    # Downloading by commit hash does not write `refs/main`, and fastembed
    # resolves its offline load through `refs/main`. Point it at the pinned
    # commit explicitly, so the ref says what was actually fetched.
    ref = cache_dir / f"models--{model_name.replace('/', '--')}" / "refs" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(revision)
    require_pinned_model(model_name, cache_dir)
    print(f"  {model_name}@{revision[:12]} fetched")


def main() -> None:
    cache_dir = model_cache_dir(sys.argv[1] if len(sys.argv) > 1 else None)
    require_symlink_support(cache_dir)
    print(f"pinned model cache: {cache_dir}")
    for model_name, revision in PINNED_MODEL_REVISIONS.items():
        fetch(model_name, revision, cache_dir)
    # Proof, not assumption: load exactly the way every other caller does.
    FastEmbedEmbedder(cache_dir=cache_dir)
    print("offline load OK")


if __name__ == "__main__":
    main()
