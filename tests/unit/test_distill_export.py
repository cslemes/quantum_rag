"""The exporter, against the real batch-v1 records with a fake planner and retriever."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from qcagent.distill.export import ExportRefused, attempt1_messages, export_dataset, fenced
from qcagent.distill.gate import GateStale, StatementRegistry
from qcagent.nodes.generator import GENERATOR_SYSTEM_PROMPT
from qcagent.state import Chunk, Requirement

BATCH = Path(__file__).resolve().parents[2] / "results" / "distill" / "batch-v1"
ORDER = [
    "qubit_permutation",
    "graph_state",
    "pauli_hamiltonian_energy",
    "diagonal_phase_ising",
    "kickback_bv_dj",
    "qaoa_p1",
    "qft",
]
ENV = {"student": "qwen2.5-coder:1.5b", "ollama": "0.40.8", "qdrant_index": "test-pin"}


def planner(state: dict) -> dict:
    return {
        "requirements": [Requirement(id="r1", kind="property", description=state["spec"][:40])],
        "status": "running",
    }


def retriever(state: dict) -> dict:
    return {
        "chunks": [
            Chunk(
                doc_id="RZGate",
                text="RZGate rotates about Z.",
                source="qiskit_api",
                library_version="1.2.4",
                score=0.0,
            )
        ]
    }


@pytest.fixture
def work(tmp_path: Path) -> Path:
    for name in ("registry.jsonl", "records.jsonl", "dataset_meta.json"):
        shutil.copy(BATCH / name, tmp_path / name)
    return tmp_path


def _export(work: Path, **kw):
    return export_dataset(
        registry=StatementRegistry(work / "registry.jsonl"),
        records_path=work / "records.jsonl",
        meta_path=work / "dataset_meta.json",
        out_path=work / "out" / "train.jsonl",
        planner=kw.pop("planner", planner),
        retriever=kw.pop("retriever", retriever),
        environment=kw.pop("environment", ENV),
        family_order=ORDER,
        **kw,
    )


def test_rows_have_the_harness_shape_and_only_labelled_records(work: Path) -> None:
    meta = _export(work)
    rows = [
        json.loads(x)
        for x in (work / "out" / "train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == meta["rows"] == 67  # batch-v1: 70 calls, 67 labelled
    row = rows[0]
    assert set(row) == {"id", "family", "messages", "completion"}
    system, user = row["messages"]
    assert system == {"role": "system", "content": GENERATOR_SYSTEM_PROMPT}
    assert user["role"] == "user" and user["content"].startswith("## Requirements")
    assert "## Retrieved context" in user["content"]
    assert row["completion"].startswith("```python\n") and row["completion"].endswith("\n```")


def test_order_follows_the_registered_family_order(work: Path) -> None:
    _export(work)
    families = [
        json.loads(x)["family"]
        for x in (work / "out" / "train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert sorted(set(families), key=families.index) == [f for f in ORDER if f in set(families)]


def test_per_family_cap(work: Path) -> None:
    meta = _export(work, per_family=4)
    assert all(n <= 4 for n in meta["per_family"].values()) and meta["rows"] == 7 * 4


def test_output_is_reproducible_and_the_hash_is_recorded(work: Path) -> None:
    first = _export(work)
    path = work / "out" / "train.jsonl"
    before = path.read_bytes()
    second = _export(work)
    assert path.read_bytes() == before and first["file_sha256"] == second["file_sha256"]
    assert first["file_sha256"] == hashlib.sha256(before).hexdigest()
    saved = json.loads((work / "out" / "train.meta.json").read_text(encoding="utf-8"))
    assert saved["environment"] == ENV and saved["teacher"]["profile"].startswith("teacher-")


def test_planner_failures_are_counted_by_reason_and_not_exported(work: Path) -> None:
    def refusing(state: dict) -> dict:
        return {"status": "rejected_input"} if "qubit" in state["spec"][:20] else planner(state)

    meta = _export(work, planner=refusing)
    assert meta["skipped"] and all(k.endswith("planner:rejected_input") for k in meta["skipped"])
    assert meta["rows"] + sum(meta["skipped"].values()) == 67


def test_an_empty_retrieval_is_not_exported(work: Path) -> None:
    meta = _export(work, retriever=lambda s: {"chunks": []})
    assert meta["rows"] == 0 and sum(meta["skipped"].values()) == 67


def test_no_environment_identity_is_refused(work: Path) -> None:
    with pytest.raises(ExportRefused):
        _export(work, environment={})


def test_a_stale_gate_is_refused(work: Path) -> None:
    lines = (work / "registry.jsonl").read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    first["gate_version"] = "0000000000000000"
    lines[0] = json.dumps(first)
    (work / "registry.jsonl").write_text("\n".join(lines) + "\n")
    with pytest.raises(GateStale):
        _export(work)


def test_a_labelled_record_outside_the_registry_is_refused(work: Path) -> None:
    rec = json.loads((work / "records.jsonl").read_text(encoding="utf-8").splitlines()[0])
    rec["statement_id"] = "ffffffffffffffff"
    with (work / "records.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    with pytest.raises(ExportRefused):
        _export(work)


def test_attempt1_messages_reports_why_a_statement_is_skipped() -> None:
    messages, reason = attempt1_messages("s", "id", lambda s: {"status": "aborted"}, retriever)
    assert messages is None and reason == "planner:aborted"
    assert fenced("  x = 1 \n") == "```python\nx = 1\n```"
