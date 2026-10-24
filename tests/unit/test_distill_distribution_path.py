"""The distribution verification path has never run on a real task. Before it
accepts any training example it is validated here on a case computed by hand, so
a later failure is never ambiguous between bad data and a bad checker.

Hand case, n = 2, p = (0.25, 0.75): qubit 0 is 1 with probability 0.25, qubit 1
with probability 0.75. Index k = q1*2 + q0:
    P(00) = 0.75 * 0.25 = 0.1875      P(01) = 0.25 * 0.25 = 0.0625
    P(10) = 0.75 * 0.75 = 0.5625      P(11) = 0.25 * 0.75 = 0.1875
(Qiskit counts keys: leftmost character = qubit 1.) Bit-reversing the register
swaps the middle two outcomes, so the checker must tell them apart: their
Hellinger fidelity is (0.1875 + 0.1875 + 2*sqrt(0.0625*0.5625))^2 = 0.5625.
"""

from __future__ import annotations

import math

import numpy as np
from qiskit import QuantumCircuit

from qcagent.distill.families import BiasedBits
from qcagent.distill.families.biased_bits import reference_counts, ry_construction
from qcagent.validators.semantic import check_distribution

HAND = {"00": 1875, "01": 625, "10": 5625, "11": 1875}  # scaled by 10,000, from the above


def _measured(p: list[float]) -> QuantumCircuit:
    circuit = ry_construction(p)
    circuit.measure_all()
    return circuit


def test_the_hand_computed_reference_is_what_the_code_builds() -> None:
    built = reference_counts([0.25, 0.75])
    total = sum(built.values())
    assert {k: v / total for k, v in built.items()} == {k: v / 10_000 for k, v in HAND.items()}


def test_the_checker_accepts_the_right_circuit_against_the_hand_reference() -> None:
    verdict = check_distribution(_measured([0.25, 0.75]), HAND)
    assert verdict.hellinger_fidelity > 0.99 and verdict.tvd < 0.05


def test_the_checker_rejects_the_bit_reversed_circuit() -> None:
    reversed_circuit = _measured([0.75, 0.25])  # qubit 0 and qubit 1 biases swapped
    verdict = check_distribution(reversed_circuit, HAND)
    assert verdict.hellinger_fidelity < 0.7
    assert math.isclose(verdict.hellinger_fidelity, 0.5625, abs_tol=0.03)


def test_the_family_accept_path_agrees() -> None:
    family = BiasedBits()
    v = next(iter(family.variations()))
    p = v.params["p"]
    assert family.accepts(v, _measured(p)).passed
    assert not family.accepts(v, _measured(list(reversed(p)))).passed
    assert not family.accepts(v, ry_construction(p)).passed  # no measurement


def test_the_sampled_check_alone_misses_a_reversal_when_biases_are_close() -> None:
    # Why the exact comparison is also required: this reversal reads above 0.99.
    p = [0.75, 0.8, 0.7]
    sampled = check_distribution(_measured(p[::-1]), reference_counts(p))
    assert sampled.hellinger_fidelity >= 0.99


def test_every_variation_is_one_where_reversal_is_detectable() -> None:
    from qcagent.distill.families.biased_bits import MIN_REVERSAL_EFFECT, product_distribution

    for v in BiasedBits().variations():
        p = v.params["p"]
        assert (
            np.max(np.abs(product_distribution(p) - product_distribution(p[::-1])))
            >= MIN_REVERSAL_EFFECT
        )
