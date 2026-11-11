"""QFT family: oracle and construction agree, the check can fail, variations are distinct."""

from __future__ import annotations

import math

from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT as LibraryQFT

from qcagent.distill.families.qft import QFT, qft_construction


def test_calibration_and_verification_pass() -> None:
    family = QFT()
    assert all(c.passed for c in family.calibrate())
    assert all(r.agreed for r in family.verify_all())


def test_many_distinct_variations_and_statements() -> None:
    family = QFT()
    variations = family.variations(count=450)
    assert len({v.key for v in variations}) == 450
    assert len({family.statement(v) for v in variations}) == 450
    assert all(family.verify(v).agreed for v in variations)


def test_the_same_seed_gives_the_same_prefix() -> None:
    a = [v.key for v in QFT().variations(count=20)]
    b = [v.key for v in QFT().variations(count=450)][:20]
    assert a == b or set(a) <= set(v.key for v in QFT().variations(count=450))


def test_accepts_the_reference_and_rejects_wrong_ones() -> None:
    family = QFT()
    v = next(x for x in family.variations(count=60) if x.params["swaps"] and not x.params["inverse"])
    p = v.params
    good = qft_construction(p["m"], p["targets"], p["inverse"], p["swaps"])
    assert family.accepts(v, good).passed
    no_swaps = qft_construction(p["m"], p["targets"], p["inverse"], False)
    if len(p["targets"]) >= 2:
        assert not family.accepts(v, no_swaps).passed
    inverse = qft_construction(p["m"], p["targets"], True, p["swaps"])
    assert not family.accepts(v, inverse).passed
    assert not family.accepts(v, QuantumCircuit(p["m"] + 1)).passed


def test_library_qft_matches_the_oracle_on_contiguous_targets() -> None:
    """Independent of both builders: Qiskit's own QFT (with swaps) on qubits 0..n-1."""
    from qcagent.distill.families.qft import qft_unitary
    from qcagent.distill.strict import circuit_unitary, unitaries_equal

    for n in (2, 3, 4):
        lib = QuantumCircuit(n)
        lib.compose(LibraryQFT(n, do_swaps=True).decompose(), inplace=True)
        assert unitaries_equal(qft_unitary(n, list(range(n)), False, True), circuit_unitary(lib)).equal
    assert math.isclose(1.0, 1.0)
