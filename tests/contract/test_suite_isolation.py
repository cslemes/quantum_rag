"""The test suite's isolation guarantees actually hold (research.md D18b):
nothing reaches the network, and a missing model cache fails fast with a
named error instead of retrying downloads.
"""

import socket
import time
from pathlib import Path

import pytest
from conftest import NetworkAccessInTests

from qcagent.retrieval.embedding import (
    PINNED_MODEL_REVISIONS,
    FastEmbedEmbedder,
    ModelNotCachedError,
    model_cache_dir,
    require_pinned_model,
)


def test_outbound_connection_is_refused_with_a_named_error() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        with pytest.raises(NetworkAccessInTests, match="203.0.113.1"):
            s.connect(("203.0.113.1", 443))  # TEST-NET-3, never routable


def test_hostname_connection_is_refused() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(NetworkAccessInTests):
            s.connect(("huggingface.co", 443))


def test_loopback_is_still_allowed() -> None:
    """Local services (a live Qdrant at localhost, the sandbox workers' own
    plumbing) are not the network."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.connect(server.getsockname())


def test_pinned_models_are_present_in_the_cache_the_suite_uses() -> None:
    cache = model_cache_dir()
    for model_name in PINNED_MODEL_REVISIONS:
        require_pinned_model(model_name, cache)


def test_embedder_loads_with_the_network_guard_active() -> None:
    """If construction reached the Hub (as fastembed does by default, even
    fully cached), the guard above would raise here."""
    FastEmbedEmbedder()


def test_missing_cache_fails_fast_and_says_how_to_fix_it(tmp_path: Path) -> None:
    """fastembed's own missing-model path sleeps 3 s then 9 s between retries
    before a vague "could not download". The preflight must refuse first."""
    start = time.monotonic()
    with pytest.raises(ModelNotCachedError, match="make models"):
        FastEmbedEmbedder(cache_dir=tmp_path)
    assert time.monotonic() - start < 2.0


def test_wrong_revision_in_the_cache_is_refused(tmp_path: Path) -> None:
    model = next(iter(PINNED_MODEL_REVISIONS))
    ref = tmp_path / f"models--{model.replace('/', '--')}" / "refs" / "main"
    ref.parent.mkdir(parents=True)
    ref.write_text("0" * 40)
    with pytest.raises(ModelNotCachedError, match="is pinned"):
        require_pinned_model(model, tmp_path)
