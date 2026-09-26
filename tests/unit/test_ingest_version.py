"""The corpus documents the pinned runtime, and that is checked, not assumed (F24).

Until T111 the unversioned (2.x) docs were scraped and every chunk stamped
`library_version="1.2.4"`. These tests pin the two halves of the fix: the
discovery only follows links to the pinned docs version, and a chunk that
documents something the runtime does not have fails verification.
"""

import qiskit

from qcagent.retrieval.ingest import (
    LIBRARY_VERSION,
    _discover_symbol_urls,
    verify_against_runtime,
)
from qcagent.state import Chunk


def _chunk(doc_id: str, source: str = "qiskit_api") -> Chunk:
    return Chunk(doc_id=doc_id, text="", source=source, library_version=LIBRARY_VERSION, score=0.0)


def test_the_pin_matches_the_installed_runtime() -> None:
    assert qiskit.__version__ == LIBRARY_VERSION


def test_discovery_follows_only_pinned_version_links() -> None:
    html = """
      <a href="/docs/en/api/qiskit/1.2/qiskit.circuit.library.HGate">HGate</a>
      <a href="/docs/en/api/qiskit/1.2/qiskit.circuit.library.HGate#h">dup</a>
      <a href="/docs/en/api/qiskit/qiskit.circuit.library.GraphStateGate">latest</a>
    """
    assert _discover_symbol_urls(html, "qiskit.circuit.library.") == [
        "https://quantum.cloud.ibm.com/docs/en/api/qiskit/1.2/qiskit.circuit.library.HGate"
    ]


def test_symbols_of_the_runtime_pass() -> None:
    failures, warnings = verify_against_runtime(
        [
            _chunk("HGate"),
            _chunk("QuantumCircuit.h"),
            _chunk("SparsePauliOp.from_list"),
            _chunk("qiskit.circuit.library.GroverOperator"),
        ]
    )
    assert failures == [] and warnings == []


def test_a_2x_only_symbol_fails() -> None:
    failures, _ = verify_against_runtime([_chunk("GraphStateGate")])
    assert failures == ["GraphStateGate: not in qiskit 1.2.4"]


def test_a_submodule_documented_as_a_function_fails() -> None:
    """The case an importability filter would pass: `grover_operator` imports
    fine in 1.2.4 and raises "'module' object is not callable" when called."""
    failures, _ = verify_against_runtime([_chunk("qiskit.circuit.library.grover_operator")])
    assert len(failures) == 1 and "submodule" in failures[0]


def test_a_missing_member_warns_but_does_not_fail() -> None:
    failures, warnings = verify_against_runtime([_chunk("QuantumCircuit.box")])
    assert failures == []
    assert warnings == ["QuantumCircuit.box: no class attribute 'box'"]


def test_migration_guide_chunks_are_exempt() -> None:
    """They document what was REMOVED, so their subjects are absent by design."""
    failures, warnings = verify_against_runtime(
        [_chunk("https://docs.quantum.ibm.com/api/qiskit/release-notes/1.0:x:1", "migration_guide")]
    )
    assert failures == [] and warnings == []
