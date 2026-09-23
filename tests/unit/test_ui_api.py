"""The interface's server surface (US6).

Two properties matter more than the endpoints themselves:

* assertion validation goes through the SAME parser the planner uses. A
  browser-side grammar that accepted what the backend refuses would leave the
  user stranded in the gap between two parsers (F11).
* the interface never writes a RunRecord. The suite owns the record of what
  the system does (Principle III); a second writer would create an
  unversioned source of numbers.
"""

import ast
from pathlib import Path

from fastapi.testclient import TestClient

from qcagent.ui.app import app

client = TestClient(app)
UI_DIR = Path("src/qcagent/ui")


def test_valid_assertions_are_echoed_back_as_the_system_read_them() -> None:
    r = client.post(
        "/api/validate", json={"assertions_text": "PROBABILITY(|00>) ~= 0.5", "n_qubits": 2}
    ).json()

    assert r["ok"] is True
    # Echoed through render_assertion — the parser's inverse — so the user
    # sees the system's READING, not their own typing.
    assert r["assertions"] == ["PROBABILITY(|00>) ~= 0.5"]


def test_a_malformed_assertion_returns_the_parsers_own_message() -> None:
    r = client.post(
        "/api/validate", json={"assertions_text": "PROBABILITY(|00>) ~~ 0.5", "n_qubits": 2}
    ).json()

    assert r["ok"] is False
    assert r["error"], "FR-013's refusal must reach the user, not a generic 'invalid'"


def test_a_width_mismatch_is_refused_here_exactly_as_the_planner_would() -> None:
    """Same parser, same rule: no implicit padding (bug 10)."""
    r = client.post(
        "/api/validate", json={"assertions_text": "PROBABILITY(|11>) ~= 0.5", "n_qubits": 3}
    ).json()

    assert r["ok"] is False
    assert "3" in r["error"]


def test_empty_input_is_not_an_error() -> None:
    r = client.post("/api/validate", json={"assertions_text": "  ", "n_qubits": 2}).json()
    assert r == {"ok": True, "assertions": []}


def test_the_page_is_served() -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "qcircuit-agent" in r.text


def test_the_ui_never_writes_a_run_record() -> None:
    """Read-only with respect to results/, enforced rather than promised."""
    forbidden = {"bench.schema", "bench.runner", "bench"}
    offenders = {}
    for path in UI_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        if bad := imported & forbidden:
            offenders[path.name] = bad
    assert not offenders, f"the interface must not import the results layer: {offenders}"


def test_the_ui_states_a_suite_seed_rather_than_inheriting_one() -> None:
    """F20: an unstated seed is what made by-hand runs incomparable to the
    suite. The interface picks a seed the suite actually runs."""
    from qcagent.ui.session import UI_SEED

    assert UI_SEED in (1, 2, 3)
