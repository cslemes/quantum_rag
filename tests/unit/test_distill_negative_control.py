"""The negative control must fire on the real pipeline, and must be able to NOT fire."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qcagent.distill.control import run_negative_control
from qcagent.distill.families import PILOT_FAMILIES, Family
from qcagent.distill.families.base import Check
from qcagent.distill.listing import snapshot_facts
from qcagent.llm.profiles import get_profile
from qcagent.validators.sandbox import WorkerPool

FACTS = snapshot_facts(
    json.loads(
        (
            Path(__file__).parent / "data" / "openrouter_listing_deepseek_v4.1_flash_1017.json"
        ).read_text()
    )
)


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=50) as p:
        yield p


def _control(pool, families=PILOT_FAMILIES, tmp_path=None):
    return run_negative_control(
        families=families,
        profile=get_profile("teacher-deepseek-v4.1-flash-1017"),
        snapshot=FACTS,
        pool=pool,
        work_dir=tmp_path,
    )


def test_every_wrong_circuit_is_rejected_with_a_reason_code_and_every_right_one_accepted(
    pool, tmp_path
) -> None:
    report = _control(pool, tmp_path=tmp_path)
    assert report["fired"] and report["halted"] is None
    assert report["wrong_rejected"] == 5 and report["correct_accepted"] == 4
    reasons = {(r["family"], r["injected"]): r["reject_reason"] for r in report["rows"]}
    assert reasons[("qubit_permutation", "wrong")] == "rejected_by_oracle:strict_unitary"
    assert reasons[("graph_state", "wrong")] == "rejected_by_oracle:strict_state"
    assert reasons[("pauli_hamiltonian_energy", "wrong")] == "rejected_by_oracle:check_energy"
    assert reasons[("independent_biased_bits", "wrong")].startswith("rejected_by_oracle:")
    assert reasons[("qubit_permutation", "unparseable")] == "static_failed:SyntaxError"
    assert all(v is None for (f, kind), v in reasons.items() if kind == "correct")


def test_the_control_does_not_fire_when_the_filter_accepts_everything(
    pool, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def accept_all(self: Family, v, circuit) -> Check:
        return Check("accept_all", True)

    for family in PILOT_FAMILIES:
        monkeypatch.setattr(type(family), "accepts", accept_all)
    report = _control(pool, tmp_path=tmp_path)
    assert report["fired"] is False
    assert report["wrong_rejected"] < 5  # the wrong circuits that parse were labelled


def test_the_control_does_not_fire_when_the_filter_rejects_everything(
    pool, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_all(self: Family, v, circuit) -> Check:
        return Check("reject_all", False)

    for family in PILOT_FAMILIES:
        monkeypatch.setattr(type(family), "accepts", reject_all)
    report = _control(pool, tmp_path=tmp_path)
    assert report["fired"] is False and report["correct_accepted"] == 0


def test_the_control_uses_no_network_and_no_real_credential(pool, tmp_path) -> None:
    report = _control(pool, tmp_path=tmp_path)
    meta = json.loads((tmp_path / "out" / "dataset_meta.json").read_text())
    assert "no network" in meta["spend_authorization"]["granted_by"]
    assert report["fired"]
