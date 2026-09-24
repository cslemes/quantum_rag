"""Checking a circuit that exists, versus generating one that doesn't.

These are different operations and the interface had merged them. Declaring an
assertion drafted from an observed distribution used to trigger a NEW
generation when the user meant "does the circuit I'm looking at satisfy this?"
— and since the generator is unreliable, the new circuit routinely violated
assertions drafted from the old one. Observed 50/50, declared it, got
failed_semantic.

A check that passes IS functional verification of that circuit with respect to
those assertions, so the report may legitimately say VERIFIED. What it must
never be is ambiguous about WHICH circuit.
"""

import io

from qiskit import QuantumCircuit, qpy

from qcagent.state import StaticResult
from qcagent.ui import session


def _store(circuit: QuantumCircuit, code: str = "qc = ...") -> str:
    buffer = io.BytesIO()
    qpy.dump(circuit, buffer)
    static = StaticResult(
        parsed=True, executed=True, transpiled=True, circuit_qpy=buffer.getvalue()
    )
    token = session._remember_run({"static": static, "code": code})
    assert token is not None
    return token


def _bell() -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    qc.measure_all()
    return qc


def test_a_holding_assertion_verifies_the_stored_circuit() -> None:
    result = session.check_stored_circuit(_store(_bell()), "PROBABILITY(|00>) ~= 0.5")

    assert result["ok"] is True
    assert result["report"]["verified"] is True


def test_a_violated_assertion_does_not_verify() -> None:
    result = session.check_stored_circuit(_store(_bell()), "PROBABILITY(|01>) ~= 0.5")

    assert result["report"]["verified"] is False
    assert [a["passed"] for a in result["report"]["assertions"]] == [False]


def test_the_verdict_names_which_circuit_it_is_about() -> None:
    """Requirement: unambiguous WHICH circuit was verified."""
    token = _store(_bell())
    result = session.check_stored_circuit(token, "PROBABILITY(|00>) ~= 0.5")

    assert result["token"] == token


def test_two_runs_do_not_bleed_into_each_other() -> None:
    """Why the token is per-run rather than "the last one": "the last one"
    changes silently under a second browser tab."""
    bell = _store(_bell())
    inert = QuantumCircuit(2)
    inert.ch(0, 1)  # controlled-H with the control in |0> — does nothing
    dead = _store(inert)

    assert session.check_stored_circuit(bell, "PROBABILITY(|00>) ~= 0.5")["report"]["verified"]
    assert not session.check_stored_circuit(dead, "PROBABILITY(|00>) ~= 0.5")["report"]["verified"]


def test_an_unknown_token_refuses_rather_than_guessing() -> None:
    result = session.check_stored_circuit("not-a-token", 'MEASURES == "00"')

    assert result["ok"] is False
    assert "no longer held" in result["error"]


def test_a_malformed_assertion_returns_the_parsers_message() -> None:
    result = session.check_stored_circuit(_store(_bell()), "PROBABILITY(|00>) ~~ 0.5")

    assert result["ok"] is False
    assert "comparator" in result["error"]


def test_empty_assertions_are_refused_not_silently_verified() -> None:
    """Zero assertions passing zero checks must never read as verification —
    the same trap `completed_unverified` exists to prevent."""
    result = session.check_stored_circuit(_store(_bell()), "   ")

    assert result["ok"] is False


def test_the_store_is_bounded() -> None:
    """A demo surface, not storage."""
    tokens = [_store(_bell()) for _ in range(session._MAX_KEPT_RUNS + 3)]

    assert len(session._runs) == session._MAX_KEPT_RUNS
    assert session.check_stored_circuit(tokens[0], 'MEASURES == "00"')["ok"] is False
    assert session.check_stored_circuit(tokens[-1], "PROBABILITY(|00>) ~= 0.5")["ok"] is True


def test_the_report_comes_from_the_one_builder() -> None:
    """Not a second report constructor: the verdict is decided in one place
    and everything reads it (F8/F10)."""
    source = __import__("pathlib").Path("src/qcagent/ui/session.py").read_text()
    assert "_build_guarantee_report" in source
    assert "GuaranteeReport(" not in source, "the UI must not assemble a report itself"
