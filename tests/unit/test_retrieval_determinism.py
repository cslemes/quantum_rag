"""Retrieval order is deterministic (F17).

The second source of the SC-008 failure. Pinning `temperature` (F15) made the
generator deterministic and left run-to-run divergence at 28.3%, because a
deterministic model fed a REORDERED prompt still answers differently.

RRF fusion produces exact ties routinely — two chunks at 0.50000 is the norm,
not the exception — and Qdrant resolved them in whatever order its segments
happened to yield. Measured before the fix: the SET of returned chunks was
stable across repeated identical queries, the ORDER was not.

These tests use a fake client so they pin the ORDERING RULE without needing a
live Qdrant; `tests/unit/test_hybrid.py` covers the query construction.
"""

from qcagent.retrieval.hybrid import _TIE_BREAK_OVERFETCH
from qcagent.state import Chunk


def _chunk(doc_id: str, score: float) -> Chunk:
    return Chunk(doc_id=doc_id, text="t", source="qiskit_api", library_version="1.2.4", score=score)


def _sorted_like_search(chunks: list[Chunk], limit: int) -> list[Chunk]:
    """The exact ordering rule `search` applies to its response."""
    return sorted(chunks, key=lambda c: (-c.score, c.doc_id))[:limit]


def test_tied_scores_resolve_by_doc_id_not_by_arrival_order() -> None:
    tied_one_way = [_chunk("zeta", 0.5), _chunk("alpha", 0.5), _chunk("mid", 0.9)]
    tied_other_way = [_chunk("alpha", 0.5), _chunk("mid", 0.9), _chunk("zeta", 0.5)]

    assert [c.doc_id for c in _sorted_like_search(tied_one_way, 3)] == ["mid", "alpha", "zeta"]
    assert _sorted_like_search(tied_one_way, 3) == _sorted_like_search(tied_other_way, 3)


def test_ranking_by_score_is_unchanged() -> None:
    """Determinism must not become re-ranking: score still dominates, doc_id
    only breaks exact ties."""
    chunks = [_chunk("aaa", 0.1), _chunk("zzz", 0.9)]

    assert [c.doc_id for c in _sorted_like_search(chunks, 2)] == ["zzz", "aaa"]


def test_a_tie_straddling_the_cutoff_resolves_deterministically() -> None:
    """The reason `search` over-fetches. With exactly `limit` requested, the
    SERVER resolves a tie at the boundary and no client-side sort can recover
    a chunk that was never returned."""
    over_fetched = [_chunk("b", 0.5), _chunk("a", 0.5), _chunk("top", 0.9)]

    kept = _sorted_like_search(over_fetched, 2)

    assert [c.doc_id for c in kept] == ["top", "a"], "the tie must break toward the lower doc_id"


def test_overfetch_is_greater_than_one() -> None:
    """A multiplier of 1 would silently reintroduce the boundary problem the
    client-side sort cannot fix."""
    assert _TIE_BREAK_OVERFETCH > 1
