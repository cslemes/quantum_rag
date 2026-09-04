"""Corpus ingestion (T031). Fetches real Qiskit documentation, chunks it
(chunking.py), embeds it (embedding.py), and upserts into Qdrant
(index.py).

SCOPE NOTE: this ingests a real, substantially-expanded corpus — the full
API surface of `qiskit.circuit.library` (every gate/circuit class),
`qiskit.quantum_info`, and `qiskit.primitives`, discovered dynamically from
each module's index page rather than hardcoded — plus the seed pages from
the first pass (migration guide, `QuantumCircuit`). It is still not the
full ~15k-unit corpus plan.md's Scale/Scope describes (PennyLane docs and
arXiv abstracts are out of scope here), but it is a genuine, real expansion
toward that scale, not a token gesture at it.

Ingestion order matters here: the failures actually observed in live runs
(T024-T030 sessions) were `qiskit.extensions` (removed in 1.0) and
`cx_decompose`/`u3` (never existed on `QuantumCircuit`). The migration
guide and the `QuantumCircuit` method reference are the two pages that
would have prevented both — ingested first, deliberately. `u3` specifically
turned out to be a corpus gap, not a retrieval gap (see `chunking.py`'s
`chunk_gate_class_page`): `U3Gate`'s own docs page carries an explicit
deprecation warning naming `u` as the replacement, and is now ingested too.
"""

import argparse
import sys

import httpx
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient

from qcagent.config import settings
from qcagent.retrieval.chunking import (
    chunk_api_reference_page,
    chunk_gate_class_page,
    chunk_migration_guide,
    dedupe_by_doc_id,
)
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.retrieval.index import ensure_collection, upsert_chunks
from qcagent.state import Chunk

LIBRARY_VERSION = "1.2.4"  # pinned qiskit version, research.md D1

_MIGRATION_GUIDE = "migration_guide"
_API_MULTI_SYMBOL = "api_multi_symbol"
_API_SINGLE_CLASS = "api_single_class"

# Priority order: migration guide + QuantumCircuit reference first (see
# module docstring's "corpus gap" note) — everything below is additional
# breadth, not the failure-preventing core.
_SOURCES: list[tuple[str, str, str | None]] = [
    (_MIGRATION_GUIDE, "https://docs.quantum.ibm.com/api/qiskit/release-notes/1.0", None),
    (
        _API_MULTI_SYMBOL,
        "https://docs.quantum.ibm.com/api/qiskit/qiskit.circuit.QuantumCircuit",
        "QuantumCircuit",
    ),
]

# Each index page lists every class/function in a module as <a> links —
# discovered dynamically (not hardcoded) so this stays correct as Qiskit
# adds/removes symbols, and so 200+ URLs don't live as a literal list in
# source. `page_type` says how the DISCOVERED pages should be chunked: gate
# pages (circuit_library) are single-class (chunk_gate_class_page); the
# quantum_info/primitives classes documented their own methods the same way
# QuantumCircuit does (chunk_api_reference_page, auto-detecting h3 vs h4).
_INDEX_PAGES: list[tuple[str, str, str]] = [
    (
        _API_SINGLE_CLASS,
        "https://docs.quantum.ibm.com/api/qiskit/circuit_library",
        "qiskit.circuit.library.",
    ),
    (
        _API_MULTI_SYMBOL,
        "https://docs.quantum.ibm.com/api/qiskit/quantum_info",
        "qiskit.quantum_info.",
    ),
    (
        _API_MULTI_SYMBOL,
        "https://docs.quantum.ibm.com/api/qiskit/primitives",
        "qiskit.primitives.",
    ),
]


def _fetch(url: str, *, client: httpx.Client) -> str:
    response = client.get(url, timeout=30.0, follow_redirects=True)
    response.raise_for_status()
    return response.text


def _discover_symbol_urls(index_html: str, href_marker: str) -> list[str]:
    """Every distinct link on an index page whose href contains
    `href_marker` (e.g. "/api/qiskit/qiskit.circuit.library.") — one entry
    per symbol page, anchor fragments stripped so the same page linked from
    multiple table-of-contents entries isn't fetched twice."""
    soup = BeautifulSoup(index_html, "lxml")
    urls: set[str] = set()
    marker = f"/api/qiskit/{href_marker}"
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if marker not in href:
            continue
        clean = href.split("#")[0]
        if clean.startswith("http"):
            urls.add(clean)
        else:
            # Relative hrefs on this docs platform resolve against
            # quantum.cloud.ibm.com, NOT the docs.quantum.ibm.com host the
            # index page itself was requested from — docs.quantum.ibm.com
            # 301-redirects there. Verified directly: prefixing with the
            # original request host produced a real 404 on every discovered
            # link; quantum.cloud.ibm.com resolves them correctly.
            urls.add(f"https://quantum.cloud.ibm.com{clean}")
    return sorted(urls)


def _class_name_from_url(url: str) -> str:
    return url.rstrip("/").rsplit(".", 1)[-1]


def _chunk_page(page_type: str, url: str, class_name: str | None, html: str) -> list[Chunk]:
    if page_type == _MIGRATION_GUIDE:
        return chunk_migration_guide(html, library_version=LIBRARY_VERSION, doc_prefix=url)
    if page_type == _API_MULTI_SYMBOL:
        return chunk_api_reference_page(
            html, library_version=LIBRARY_VERSION, class_name=class_name
        )
    # _API_SINGLE_CLASS
    chunk = chunk_gate_class_page(html, library_version=LIBRARY_VERSION)
    return [chunk] if chunk is not None else []


def _build_source_list(client: httpx.Client) -> list[tuple[str, str, str | None]]:
    sources: list[tuple[str, str, str | None]] = list(_SOURCES)
    for page_type, index_url, href_marker in _INDEX_PAGES:
        index_html = _fetch(index_url, client=client)
        discovered = _discover_symbol_urls(index_html, href_marker)
        print(f"  {index_url} -> discovered {len(discovered)} symbol pages", file=sys.stderr)
        for url in discovered:
            class_name = _class_name_from_url(url) if page_type == _API_MULTI_SYMBOL else None
            sources.append((page_type, url, class_name))
    return sources


def collect_chunks() -> list[Chunk]:
    """Fetches every configured and discovered source and returns the
    deduplicated chunk set. Separated from `main()` so tests can exercise
    it against local HTML fixtures instead of live network calls.

    A single page's fetch failing (404, timeout) is logged and skipped, not
    fatal — at this scale (200+ pages), one dead link must not abort the
    whole ingestion run.
    """
    all_chunks: list[Chunk] = []
    with httpx.Client() as client:
        sources = _build_source_list(client)
        print(f"Total source pages: {len(sources)}", file=sys.stderr)
        for page_type, url, class_name in sources:
            try:
                html = _fetch(url, client=client)
            except httpx.HTTPError as exc:
                print(f"  SKIP {url}: {exc}", file=sys.stderr)
                continue
            chunks = _chunk_page(page_type, url, class_name, html)
            print(f"  {url} -> {len(chunks)} chunks", file=sys.stderr)
            all_chunks.extend(chunks)
    return dedupe_by_doc_id(all_chunks)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recreate", action="store_true", help="Drop and recreate the collection")
    args = parser.parse_args()

    print("Fetching and chunking sources...", file=sys.stderr)
    chunks = collect_chunks()
    print(f"Total chunks after dedup: {len(chunks)}", file=sys.stderr)

    print("Embedding...", file=sys.stderr)
    embedder = FastEmbedEmbedder()
    dense_vectors = embedder.embed_documents([c.text for c in chunks])
    sparse_vectors = embedder.embed_sparse_documents([c.text for c in chunks])

    client = QdrantClient(url=settings.qdrant_url)
    ensure_collection(client, embedder.dense_dim, recreate=args.recreate)
    written = upsert_chunks(client, chunks, dense_vectors, sparse_vectors)
    print(f"Upserted {written} points into 'qdocs'.", file=sys.stderr)


if __name__ == "__main__":
    main()
