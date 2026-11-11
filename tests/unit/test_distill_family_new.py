"""Diagonal-phase, kickback (BV/DJ) and QAOA p=1 families: they verify, the check can fail."""

from __future__ import annotations

import pytest
from qiskit import QuantumCircuit

from qcagent.distill.families.diagonal_phase import DiagonalPhase, ladder_circuit
from qcagent.distill.families.kickback import KickbackBvDj, kickback_circuit
from qcagent.distill.families.qaoa import QaoaP1, qaoa_gates

FAMILIES = [DiagonalPhase(), KickbackBvDj(), QaoaP1()]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_calibration_and_verification(family) -> None:
    assert all(c.passed for c in family.calibrate())
    assert all(r.agreed for r in family.verify_all())


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_450_distinct_variations_that_verify(family) -> None:
    variations = family.variations(count=450)
    assert len({v.key for v in variations}) == 450
    assert len({family.statement(v) for v in variations}) == 450
    assert all(family.verify(v).agreed for v in variations)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.name)
def test_prefix_is_stable(family) -> None:
    assert [v.key for v in family.variations(20)] == [v.key for v in family.variations(450)][:20]


def test_wrong_circuits_are_rejected() -> None:
    d = DiagonalPhase()
    v = d.variations(5)[0]
    p = v.params
    assert d.accepts(v, ladder_circuit(p["n"], p["terms"], p["coeffs"])).passed
    assert not d.accepts(v, ladder_circuit(p["n"], p["terms"], [-c for c in p["coeffs"]])).passed

    k = KickbackBvDj()
    v = k.variations(5)[0]
    p = v.params
    assert k.accepts(v, kickback_circuit(p["n"], p["s"], p["c"])).passed
    other = (p["s"] % ((1 << p["n"]) - 1)) + 1
    assert other != p["s"] or p["n"] == 1
    if other != p["s"]:
        assert not k.accepts(v, kickback_circuit(p["n"], other, p["c"])).passed
    assert not k.accepts(v, QuantumCircuit(p["n"] + 1)).passed

    q = QaoaP1()
    v = q.variations(5)[0]
    p = v.params
    assert q.accepts(v, qaoa_gates(p["n"], p["edges"], p["gamma"], p["beta"])).passed
    assert not q.accepts(v, qaoa_gates(p["n"], p["edges"], p["gamma"] + 0.05, p["beta"])).passed
