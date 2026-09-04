"""Code-aware chunking (T032, T033). See research.md D6.

Chunking by symbol: signature + docstring + example stay in the SAME unit.
Window/token-based chunking would split an example from the exact signature
that prevents API hallucination — a chunk with the example but not the
signature is worse than no chunk at all.

Three page shapes on docs.quantum.ibm.com map to three extraction
strategies (verified against the live pages, not guessed):
  - Multi-symbol API reference (e.g. the QuantumCircuit class page): each
    `<h4>` is one method, and everything up to the next heading — signature,
    docstring, parameters — lives in the sibling `<div>` right after it.
  - Single-class gate pages (e.g. RZGate, RXGate): the class's own
    signature/docstring/matrix lives between the `<h1>` and the first
    `<h2>` ("Attributes") — the Attributes/Methods sections below that are
    boilerplate inherited from `Gate`/`Instruction`, not worth a chunk.
  - Release notes / migration guides: each `<li>` under an "... Upgrade
    Notes" `<h3>` is one self-contained removal/rename note.

**Register prefix** (research.md D17's fix): every chunk's indexed text is
prefixed with `[method]`, `[class]`, or `[migration]`. Measured cause: at
1,020 chunks, `QuantumCircuit.cx` (a method) and `CXGate` (the class the
method wraps) describe the same operation in near-identical language —
nothing in the raw text told the dense embedding they're different kinds of
answer, and it started returning the class page for method-shaped
questions ("how do I add a CNOT gate?"). The register token gives the
embedding a cheap, explicit signal the raw prose doesn't otherwise carry.
"""

import re
from collections.abc import Sequence

from bs4 import BeautifulSoup
from bs4.element import Tag

from qcagent.state import Chunk

_STOP_HEADINGS = {"h1", "h2", "h3", "h4"}

# D6: "if it exceeds the limit, split by example, replicating the signature
# in each piece's header." Measured against the real corpus: only 12 of
# 1020 chunks exceed 4000 chars (2 exceed 8000) — a handful of outliers
# (verbose methods like `QuantumCircuit.compose`, `SparsePauliOp` variants),
# not a systemic sizing problem, and one of those outliers alone was enough
# to OOM-kill the embedding step (a long chunk sharing a padded ONNX batch
# with others multiplies cost quadratically with sequence length).
#
# THIS IS ONLY A PARTIAL FIX (research.md D17-2), not what D6 actually asks
# for. `_cap_length` hard-truncates from the end — the register/doc_id/
# signature is always at the START of `text` (see `_with_register` below),
# so that survives, but usage EXAMPLES conventionally come at the end of a
# docstring, right where this cuts. That is exactly the content D6 exists to
# protect ("a chunk with the example but not the signature is worse than no
# chunk" — the inverse, a chunk with the signature but not the example, is
# also degraded, just less obviously). Harmless at 12 affected chunks;
# grows as the corpus does. Real per-example splitting, not truncation, is
# still owed here before this scales further.
_MAX_CHUNK_CHARS = 4000


def _cap_length(body: str) -> str:
    if len(body) <= _MAX_CHUNK_CHARS:
        return body
    return body[:_MAX_CHUNK_CHARS] + " …[truncated]"


def _with_register(register: str, label: str, body: str) -> str:
    """`"[{register}] {label} — {body}"` — see module docstring's "Register
    prefix" note. `register` and `label` both sit before the em dash, so
    they survive `_cap_length`'s truncation (applied to `body` before this
    wraps it, at every call site) exactly like the bare doc_id/signature did
    before this change.
    """
    return f"[{register}] {label} — {body}"


def _collect_until(start: Tag, stop_tags: set[str]) -> str:
    """Text of every sibling after `start`, up to (not including) the next
    tag whose name is in `stop_tags`."""
    parts: list[str] = []
    current = start
    while True:
        sibling = current.find_next_sibling()
        if sibling is None or not isinstance(sibling, Tag):
            break
        if sibling.name in stop_tags:
            break
        text = sibling.get_text(" ", strip=True)
        if text:
            parts.append(text)
        current = sibling
    return "\n\n".join(parts)


def chunk_api_reference_page(
    html: str, *, library_version: str, class_name: str | None = None
) -> list[Chunk]:
    """Chunks a multi-symbol API reference page into one `Chunk` per symbol.
    `class_name` (e.g. "QuantumCircuit"), when given, prefixes `doc_id` so
    `qc.cx_decompose` and a hypothetical unrelated top-level `cx_decompose`
    don't collide.

    The per-method heading level is NOT the same across every page —
    verified against two real, differently-laid-out pages: `QuantumCircuit`
    nests methods three levels deep (`<h2>` category -> `<h3>` subcategory ->
    `<h4>` method), while `Operator` lists them two levels deep (`<h2>`
    "Methods" -> `<h3>` method) with no `<h4>` at all. Auto-detects: `<h4>`
    if the page has any, `<h3>` otherwise — guessing one fixed level would
    silently yield zero chunks on whichever page shape it guessed wrong.
    """
    soup = BeautifulSoup(html, "lxml")
    symbol_tag = "h4" if soup.find("h4") is not None else "h3"
    chunks: list[Chunk] = []
    for heading in soup.find_all(symbol_tag):
        raw_id = heading.get("id")
        symbol = str(raw_id) if raw_id else heading.get_text(strip=True)
        if not symbol:
            continue
        body = _collect_until(heading, _STOP_HEADINGS)
        if not body:
            continue
        doc_id = f"{class_name}.{symbol}" if class_name else symbol
        deprecated = bool(_GATE_DEPRECATED_RE.search(body))
        replacement = None
        if deprecated:
            match = _GATE_REPLACEMENT_METHOD_RE.search(body)
            if match:
                replacement = f"{class_name}.{match.group(1)}()" if class_name else match.group(1)
        chunks.append(
            Chunk(
                doc_id=doc_id,
                text=_with_register("method", doc_id, _cap_length(body)),
                source="qiskit_api",
                library_version=library_version,
                deprecated=deprecated,
                replacement=replacement,
                score=0.0,  # ingestion-time placeholder; score is a query-time concept
            )
        )
    return chunks


_GATE_DEPRECATED_RE = re.compile(r"is deprecated", re.IGNORECASE)
# The deprecation warning on a gate-class page reads "... the following
# replacements should be used ... circuit = QuantumCircuit(1) circuit.u
# (theta, phi, lambda)" — the method call right after the worked example is
# the actual replacement (confirmed against the real U3Gate page: this
# extracts "u", matching D7's "u3 -> u" case exactly).
_GATE_REPLACEMENT_METHOD_RE = re.compile(r"circuit\s*\.\s*(\w+)\s*\(")


def chunk_gate_class_page(html: str, *, library_version: str) -> Chunk | None:
    """Chunks a single-class gate page (RZGate, RXGate, U3Gate, ...) into one
    chunk covering the class's own signature, docstring, and matrix — the
    Attributes/Methods sections below that are inherited boilerplate from
    `Gate`/`Instruction`, not distinguishing content.

    Some gate classes carry their own deprecation warning in that docstring
    (e.g. U3Gate: "This gate is deprecated... circuit.u(theta, phi, lambda)")
    — a real, live case of D7's "obsolete material must be LABELED, not
    omitted": U3Gate still exists as a page (Qiskit doesn't purge deprecated
    class docs), so the corpus can and must carry it deprecated=True with
    its replacement, not simply lack it.
    """
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if h1 is None:
        return None
    class_name = h1.get_text(strip=True)
    body = _collect_until(h1, {"h2"})
    if not body:
        return None

    deprecated = bool(_GATE_DEPRECATED_RE.search(body))
    replacement = None
    if deprecated:
        match = _GATE_REPLACEMENT_METHOD_RE.search(body)
        if match:
            replacement = f"QuantumCircuit.{match.group(1)}()"

    return Chunk(
        doc_id=class_name,
        text=_with_register("class", class_name, _cap_length(body)),
        source="qiskit_api",
        library_version=library_version,
        deprecated=deprecated,
        replacement=replacement,
        score=0.0,
    )


# "Removed the qiskit.extensions module" / "Removed `Instruction.qasm`...
# use qiskit.qasm2.dump() instead" — best-effort, not exhaustive. A miss
# just leaves deprecated=False (informational chunk still ingested); a
# false positive would mislabel current material as obsolete, so both
# patterns require an explicit "Removed"/"Renamed" verb, not just any
# mention of a symbol.
_RENAMED_RE = re.compile(r"Renamed\s+`?([\w.]+)`?\s+to\s+`?([\w.()]+)`?")
_REMOVED_WITH_REPLACEMENT_RE = re.compile(
    r"Removed(?:\s+the)?\s+`?([\w.]+)`?.{0,200}?[Uu]se\s+`?([\w.()]+)`?\s+instead", re.DOTALL
)
_REMOVED_RE = re.compile(r"Removed(?:\s+the)?\s+`?([\w.]+)`?")


def _detect_deprecation(text: str) -> tuple[bool, str | None]:
    match = _RENAMED_RE.search(text)
    if match:
        return True, match.group(2)
    match = _REMOVED_WITH_REPLACEMENT_RE.search(text)
    if match:
        return True, match.group(2)
    match = _REMOVED_RE.search(text)
    if match:
        return True, None
    return False, None


def chunk_migration_guide(html: str, *, library_version: str, doc_prefix: str) -> list[Chunk]:
    """Chunks a release-notes/migration page: one chunk per `<li>` under an
    "... Upgrade Notes" `<h3>` section. FR-014/D7: a note that reads as a
    removal or rename is tagged `deprecated=True` with its `replacement`
    when the text states one — obsolete material must reach the generator
    LABELED as unusable, not silently included as if it were current.
    """
    soup = BeautifulSoup(html, "lxml")
    chunks: list[Chunk] = []
    index = 0
    for h3 in soup.find_all("h3"):
        heading = h3.get_text(strip=True)
        if "Upgrade Notes" not in heading:
            continue
        node: Tag = h3
        while True:
            sibling = node.find_next_sibling()
            if sibling is None or sibling.name in ("h2", "h3"):
                break
            node = sibling
            if node.name != "ul":
                continue
            for li in node.find_all("li", recursive=False):
                text = li.get_text(" ", strip=True)
                if not text:
                    continue
                index += 1
                deprecated, replacement = _detect_deprecation(text)
                chunks.append(
                    Chunk(
                        doc_id=f"{doc_prefix}:{heading}:{index}",
                        text=_with_register("migration", heading, text),
                        source="migration_guide",
                        library_version=library_version,
                        deprecated=deprecated,
                        replacement=replacement,
                        score=0.0,
                    )
                )
    return chunks


def dedupe_by_doc_id(chunks: Sequence[Chunk]) -> list[Chunk]:
    """Later chunks win — used when combining multiple ingestion passes
    that might redundantly cover the same symbol."""
    by_id = {c.doc_id: c for c in chunks}
    return list(by_id.values())
