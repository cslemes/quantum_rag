"""The leakage gate and the registry: what it rejects, what it cannot be talked
out of, and that the calibration on file is what the suite gives."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from qiskit import QuantumCircuit

from qcagent.distill.families import PILOT_FAMILIES, BuilderDisagreement, QubitPermutations
from qcagent.distill.gate import (
    ROOT,
    GateStale,
    NotAdmitted,
    StatementRegistry,
    calibrate,
    circuit_leak_check,
    load_test_tasks,
    review_queue,
    statement_id,
)


@pytest.fixture(scope="module")
def tasks() -> dict:
    return load_test_tasks()


@pytest.fixture
def registry(tmp_path: Path) -> StatementRegistry:
    return StatementRegistry(tmp_path / "registry.jsonl")


def test_the_calibration_on_file_is_what_the_suite_gives(tasks) -> None:
    on_file = json.loads((ROOT / "bench" / "leakage_calibration.json").read_text())
    assert on_file == asdict(calibrate(tasks))
    assert on_file["twin_pairs"] == 60


def test_the_least_similar_twin_rule_is_unusable_and_the_recorded_threshold_is_not_it(
    tasks,
) -> None:
    cal = calibrate(tasks)
    assert cal.twin_min < 0.01 < cal.reject_at  # the first design's rule would reject everything
    assert cal.review_at < cal.reject_at


def test_all_eighty_pilot_statements_are_admitted_with_both_numbers_recorded(registry) -> None:
    for family in PILOT_FAMILIES:
        registry.admit_family(family)
    entries = registry.entries()
    assert len(entries) == 80 and {e["verdict"] for e in entries} == {"pass"}
    assert all(len(e["nearest"]) == 3 and e["semantic"].startswith("not measured") for e in entries)
    assert len(registry.export()) == 80


def test_a_copy_of_a_test_prompt_is_rejected_and_logged_without_test_text(registry, tasks) -> None:
    prompt = tasks["bell_phi_plus_2q"]["prompt"]
    judged = registry._judge(prompt + " Please be careful.", "some_new_family")
    assert judged["verdict"] == "reject" and judged["nearest"][0]["task_id"].startswith("bell_phi")


def test_a_light_edit_lands_in_review_or_rejection(registry, tasks) -> None:
    prompt = tasks["bell_phi_plus_2q"]["prompt"].replace("Build a 2-qubit", "Construct a 2-qubit")
    assert registry._judge(prompt, "some_new_family")["verdict"] in ("review", "reject")


def test_a_family_that_is_a_task_id_family_of_the_suite_is_rejected(registry) -> None:
    judged = registry._judge("Something unrelated entirely about apples.", "grover")
    assert judged["verdict"] == "reject" and "structural" in judged["reasons"][0]


def test_a_family_whose_builders_disagree_admits_nothing(registry, monkeypatch) -> None:
    import qcagent.distill.families.permutations as module

    monkeypatch.setattr(module, "swap_construction", lambda pi: QuantumCircuit(len(pi)))
    with pytest.raises(BuilderDisagreement):
        registry.admit_family(QubitPermutations())
    assert registry.entries() == []


def test_generation_gets_a_statement_only_by_id_and_only_if_it_passed(registry) -> None:
    registry.admit_family(QubitPermutations())
    entry = registry.entries()[0]
    assert registry.require_pass(entry["id"])["statement"] == entry["statement"]
    with pytest.raises(NotAdmitted):
        registry.require_pass(statement_id("a string that never went through the gate"))


def test_a_statement_written_around_the_gate_is_caught_on_export(registry) -> None:
    registry.admit_family(QubitPermutations())
    entries = registry.entries()
    tampered = dict(entries[0], statement=load_test_tasks()["bell_phi_plus_2q"]["prompt"])
    registry.path.write_text("".join(json.dumps(e) + "\n" for e in [tampered, *entries[1:]]))
    with pytest.raises(NotAdmitted):
        registry.export()


def test_a_change_to_the_test_set_invalidates_earlier_passes(registry, tmp_path) -> None:
    registry.admit_family(QubitPermutations())
    entry = registry.entries()[0]
    registry.gate_version = "a-different-test-set"
    with pytest.raises(GateStale):
        registry.require_pass(entry["id"])
    with pytest.raises(GateStale):
        registry.export()


def test_a_review_is_recorded_and_decides(registry) -> None:
    registry.admit_family(QubitPermutations())
    entries = registry.entries()
    entries[0]["verdict"] = "review"
    registry.path.write_text("".join(json.dumps(e) + "\n" for e in entries))
    registry.record_review(entries[0]["id"], "accept", "reviewer-1")
    assert registry.require_pass(entries[0]["id"])["reviewer"]["by"] == "reviewer-1"


def test_the_review_queue_has_the_closest_pairs_and_a_sample_from_below(registry) -> None:
    registry.admit_family(QubitPermutations())
    queue = review_queue(registry, top=100, random_below=50)
    assert len(queue["closest"]) == 100 and len(queue["random_below_band"]) == 50
    scores = [p["score"] for p in queue["closest"]]
    assert scores == sorted(scores, reverse=True)


def test_circuit_leak_check_finds_a_bell_circuit_against_the_references() -> None:
    bell = QuantumCircuit(2)
    bell.h(0)
    bell.cx(0, 1)
    result = circuit_leak_check("statevector", bell)
    assert result["evaluated"] and "bell_phi_plus_2q" in result["matches"]


def test_circuit_leak_check_does_not_match_a_reversed_register_reference() -> None:
    # |01>+|10> (psi+) is a reference; the same state built with the roles of
    # the qubits exchanged is the same state, but |10>+|11> is not any reference.
    other = QuantumCircuit(2)
    other.x(1)
    other.h(0)
    assert circuit_leak_check("statevector", other)["matches"] == []


def test_circuit_leak_check_says_when_it_cannot_evaluate() -> None:
    result = circuit_leak_check("distribution", QuantumCircuit(2))
    assert result["evaluated"] is False and result["matches"] == []
