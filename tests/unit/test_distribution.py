"""The output distribution (FR-018) — descriptive, never evaluative.

The load-bearing property is the draft assertion: the affordance turns an
observed outcome into declarable grammar, and if that grammar failed when
checked, the interface would be handing users broken assertions. Worse than no
affordance. So the tests parse each draft with the REAL parser and evaluate it
against the circuit it came from.
"""

import numpy as np
import pytest
from qiskit import QuantumCircuit
from qiskit.circuit import Parameter

from qcagent.validators.assertions import evaluate_assertions, parse_assertions
from qcagent.validators.circuits import NotEvaluable
from qcagent.validators.distribution import (
    DEFAULT_TOP_K,
    Outcome,
    draft_assertion,
    outcome_distribution,
)


def _bell(measured: bool = True) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    if measured:
        qc.measure_all()
    return qc


# --- what it reports -------------------------------------------------------


def test_a_measured_circuit_is_read_exactly_not_sampled() -> None:
    """A final measurement samples the prepared state without changing it, so
    the exact distribution is the same quantity the shots would estimate —
    minus noise the system does not actually have."""
    result = outcome_distribution(_bell())

    assert result.source == "exact"
    assert [(o.bitstring, round(o.probability, 6)) for o in result.outcomes] == [
        ("00", 0.5),
        ("11", 0.5),
    ]


def test_impossible_outcomes_are_omitted_not_listed_as_zero() -> None:
    """Floating point leaves 1e-33 residue on exactly-zero amplitudes.
    Listing those implies the circuit can produce them."""
    result = outcome_distribution(_bell())

    assert {o.bitstring for o in result.outcomes} == {"00", "11"}
    assert result.total_outcomes == 2


def test_large_registers_are_truncated_with_the_remainder_stated() -> None:
    """2^n is unreadable past a few qubits, but silently dropping mass would
    misrepresent the circuit."""
    qc = QuantumCircuit(6)
    qc.h(range(6))

    result = outcome_distribution(qc, top_k=4)

    assert result.shown == 4
    assert result.total_outcomes == 64
    assert result.truncated
    assert result.omitted_probability == pytest.approx(60 / 64, abs=1e-9)


def test_ordering_is_total_so_ties_do_not_depend_on_dict_order() -> None:
    """64 equal probabilities: the order must come from the data, not from
    iteration order (the F17 lesson, applied here)."""
    qc = QuantumCircuit(6)
    qc.h(range(6))

    first = [o.bitstring for o in outcome_distribution(qc, top_k=8).outcomes]
    again = [o.bitstring for o in outcome_distribution(qc, top_k=8).outcomes]

    assert first == again
    assert first == sorted(first), "equal probabilities tie-break by bitstring"


def test_a_circuit_with_no_distribution_says_so() -> None:
    qc = QuantumCircuit(2)
    qc.rx(Parameter("theta"), 0)

    assert isinstance(outcome_distribution(qc), NotEvaluable)


def test_a_mid_circuit_measurement_falls_back_to_sampling() -> None:
    """No pure state to read exactly, but the circuit still HAS a
    distribution — reporting nothing would be wrong."""
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.measure_all()
    qc.cx(0, 1)

    result = outcome_distribution(qc)

    assert not isinstance(result, NotEvaluable)
    assert result.source == "sampled"


# --- the draft assertion, which must actually hold -------------------------


@pytest.mark.parametrize(
    ("build", "n"),
    [
        (lambda: _bell(), 2),
        (lambda: _bell(measured=False), 2),
        (lambda: _uniform(3), 3),
        (lambda: _w_state(), 3),
    ],
    ids=["bell-measured", "bell-bare", "uniform-3q", "w-state"],
)
def test_every_draft_parses_and_holds_against_its_own_circuit(build, n) -> None:
    """The property the affordance lives or dies on."""
    circuit = build()
    result = outcome_distribution(circuit)

    for outcome in result.outcomes:
        draft = draft_assertion(outcome, n_qubits=n)
        parsed = parse_assertions(draft, n)  # must parse
        verdicts = evaluate_assertions(parsed, circuit)
        assert [v.passed for v in verdicts] == [True], f"{draft} did not hold"


def test_a_certain_outcome_drafts_as_measures() -> None:
    """MEASURES reads better aloud than PROBABILITY ~= 1.0 and carries its own
    looser certainty tolerance."""
    qc = QuantumCircuit(2)
    qc.x(0)
    qc.measure_all()

    (outcome,) = outcome_distribution(qc).outcomes

    assert draft_assertion(outcome, n_qubits=2) == 'MEASURES == "01"'


def test_drafts_are_rounded_to_something_a_person_would_write() -> None:
    """A Bell amplitude comes back as 0.4999999999999999. Drafting that is
    correct and unreadable; 0.5 is within 1.1e-16 and holds."""
    outcome = outcome_distribution(_bell()).outcomes[0]

    assert draft_assertion(outcome, n_qubits=2) == "PROBABILITY(|00>) ~= 0.5"


def test_rounding_never_coarsens_past_the_grammars_tolerance() -> None:
    """One third cannot round to 0.3333 — that is 3.3e-5 away and `~=`
    compares within 1e-9. The rounding is checked, not assumed."""
    draft = draft_assertion(Outcome("001", 1 / 3), n_qubits=3)

    assert draft == "PROBABILITY(|001>) ~= 0.3333333333"


def test_the_default_top_k_is_small_enough_to_read() -> None:
    assert DEFAULT_TOP_K <= 10


def _uniform(n: int) -> QuantumCircuit:
    qc = QuantumCircuit(n)
    qc.h(range(n))
    return qc


def _w_state() -> QuantumCircuit:
    qc = QuantumCircuit(3)
    qc.ry(2 * np.arccos(1 / np.sqrt(3)), 0)
    qc.ch(0, 1)
    qc.cx(1, 2)
    qc.cx(0, 1)
    qc.x(0)
    return qc
