"""QFT family: oracle and construction agree, the check can fail, variations are distinct."""

from __future__ import annotations

import cmath
import math

import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit.library import QFT as LibraryQFT

from qcagent.distill.families.base import Variation
from qcagent.distill.families.qft import QFT, qft_construction, qft_unitary
from qcagent.distill.strict import circuit_unitary, unitaries_equal


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
    v = next(
        x for x in family.variations(count=60) if x.params["swaps"] and not x.params["inverse"]
    )
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
    for n in (2, 3, 4):
        lib = QuantumCircuit(n)
        lib.compose(LibraryQFT(n, do_swaps=True).decompose(), inplace=True)
        oracle = qft_unitary(n, list(range(n)), False, True)
        assert unitaries_equal(oracle, circuit_unitary(lib)).equal
    assert math.isclose(1.0, 1.0)


def _statement_formula(m: int, targets: list[int], inverse: bool, swaps: bool) -> np.ndarray:
    """The matrix the STATEMENT spells out, written a third time, sharing no code with the oracle
    or the construction:  |x> -> N^-1/2 sum_y exp(+-2 pi i x y / N) |y>  with the SWAP layer,
    |bitrev(y)>  without it; bit j of x is qubit targets[j]; the other qubits are untouched."""
    n = len(targets)
    size = 1 << n
    sign = -1 if inverse else 1
    mask = sum(1 << q for q in targets)
    matrix = np.zeros((1 << m, 1 << m), dtype=complex)
    for b in range(1 << m):
        x = sum(((b >> q) & 1) << j for j, q in enumerate(targets))
        for y in range(size):
            shown = y if swaps else int(format(y, f"0{n}b")[::-1], 2)
            out = (b & ~mask) | sum(((shown >> j) & 1) << q for j, q in enumerate(targets))
            matrix[out, b] = cmath.exp(sign * 2j * math.pi * x * y / size) / math.sqrt(size)
    return matrix


def test_the_statement_formula_is_the_oracle_in_every_cell() -> None:
    """Regression for train-v1. In the inverse / no-SWAP cell the oracle was the adjoint of the
    no-swap transform while the statement gave this formula: 106 answers that satisfied their
    statement were rejected and 4 that did not were accepted. `verify` cannot see that: it
    compares the oracle with the construction, and neither is read off the statement."""
    family = QFT()
    cells = set()
    for v in family.variations(count=120):
        p = v.params
        n = len(p["targets"])
        sign = "-" if p["inverse"] else "+"
        text = family.statement(v)
        # the formula tested is the one in the text: if the wording changes, rewrite both
        assert f"sum over y of exp({sign}2*pi*i*x*y/2^{n}) |y>" in text
        assert (f"exp({sign}2*pi*i*x*y/2^{n}) |bitrev(y)>" in text) == (not p["swaps"])
        expected = _statement_formula(p["m"], p["targets"], p["inverse"], p["swaps"])
        oracle = qft_unitary(p["m"], p["targets"], p["inverse"], p["swaps"])
        assert unitaries_equal(oracle, expected).equal, p
        cells.add((p["inverse"], p["swaps"]))
    assert cells == {(False, False), (False, True), (True, False), (True, True)}


def test_inverse_without_swaps_is_the_negated_ladder_not_the_reversed_circuit() -> None:
    """What the teacher wrote 106 times in train-v1, and what was wrongly required instead."""
    family = QFT()
    for n in (2, 3, 4):
        params = {"m": n, "targets": list(range(n)), "inverse": True, "swaps": False}
        v = Variation("qft", 0, params)
        negated = QuantumCircuit(n)  # the forward gate order, every angle negated
        for j in range(n - 1, -1, -1):
            negated.h(j)
            for k in range(j - 1, -1, -1):
                negated.cp(-math.pi / 2 ** (j - k), k, j)
        assert family.accepts(v, negated).passed
        adjoint = QuantumCircuit(n)  # Qiskit's QFT(do_swaps=False).inverse(): input bit-reversed
        adjoint.compose(LibraryQFT(n, do_swaps=False).inverse().decompose(), inplace=True)
        assert not family.accepts(v, adjoint).passed


def test_the_other_three_cells_are_qiskits_library_conventions() -> None:
    for n in (2, 3, 4):
        targets = list(range(n))
        for inverse, swaps, library in (
            (False, False, LibraryQFT(n, do_swaps=False)),
            (True, True, LibraryQFT(n, do_swaps=True).inverse()),
        ):
            lib = QuantumCircuit(n)
            lib.compose(library.decompose(), inplace=True)
            oracle = qft_unitary(n, targets, inverse, swaps)
            assert unitaries_equal(oracle, circuit_unitary(lib)).equal


def test_the_control_circuits_follow_the_contract_in_every_cell() -> None:
    from qcagent.distill.control import correct_code, wrong_code

    family = QFT()
    cells = set()
    for v in family.variations(count=40):
        if len(v.params["targets"]) < 2:
            continue
        for builder, expected in ((correct_code, True), (wrong_code, False)):
            source = builder(family, v).removeprefix("```python\n").removesuffix("\n```")
            scope: dict = {}
            exec(source, scope)  # the control's own code, written by this repository
            assert family.accepts(v, scope["qc"]).passed is expected, (builder.__name__, v.params)
        cells.add((v.params["inverse"], v.params["swaps"]))
    assert len(cells) == 4
