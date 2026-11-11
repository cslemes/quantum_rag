"""The three older families scale past the pilot's 20 without changing the pilot's 20."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qcagent.distill.families.graph_states import GraphStates
from qcagent.distill.families.pauli_energy import PauliEnergy
from qcagent.distill.families.permutations import QubitPermutations

REGISTRY = Path(__file__).resolve().parents[2] / "results/distill/pilot-v1/registry.jsonl"
FAMILIES = [QubitPermutations(), GraphStates(), PauliEnergy()]


def _pilot_keys(name: str) -> set[str]:
    rows = [json.loads(line) for line in REGISTRY.read_text().splitlines() if line.strip()]
    return {r["variation_key"] for r in rows if r["family"] == name}


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_first_twenty_are_the_recorded_pilot_variations(family) -> None:
    recorded = _pilot_keys(family.name)
    assert len(recorded) == 20
    assert {v.key for v in family.variations(20)} == recorded
    assert {v.key for v in family.variations(450)[:20]} == recorded


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_450_distinct_variations_that_verify(family) -> None:
    variations = family.variations(count=450)
    assert len({v.key for v in variations}) == 450
    assert len({family.statement(v) for v in variations}) == 450
    assert all(family.verify(v).agreed for v in variations)
