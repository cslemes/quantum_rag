"""Regression test: the generator must render a semantic ErrorRecord's
structural-diff payload as readable text, not dump the raw dict — a retry
needs to be able to read "you used x where h/cx were expected", not parse
Python repr syntax.
"""

from qcagent.nodes.generator import _render_errors
from qcagent.state import ErrorRecord


def _wrong_gate_decomposition_error(iteration: int) -> ErrorRecord:
    return ErrorRecord(
        iteration=iteration,
        stage="semantic",
        error_type="WrongGateDecomposition",
        message="unitária diverge da referência (fidelidade=0.3536, método=exact)",
        payload={
            "expected_n_qubits": 2,
            "actual_n_qubits": 2,
            "expected_gate_counts": {"h": 1, "cx": 1},
            "actual_gate_counts": {"x": 2},
            "reversed_bit_order_matches": False,
            "direct_fidelity": 0.3536,
            "reversed_bit_order_fidelity": 0.3536,
        },
    )


def test_structural_diff_is_rendered_as_readable_text_not_a_dict_dump() -> None:
    rendered = _render_errors([_wrong_gate_decomposition_error(iteration=1)])

    # Not a raw dict dump: no Python repr punctuation from a bare `payload`.
    assert "{'expected_gate_counts'" not in rendered
    assert "expected_gate_counts=" not in rendered

    # The actionable content is present, spelled out per gate.
    assert "qubits: expected=2, actual=2" in rendered
    assert "h: 1 vs 0" in rendered
    assert "cx: 1 vs 0" in rendered
    assert "x: 0 vs 2" in rendered
    assert "reversed-bit-order check: also failed" in rendered


def test_diff_across_multiple_attempts_shows_no_progress_explicitly() -> None:
    """The exact real-run symptom that motivated this: fidelity going
    0.50 -> 0.00 -> 0.00 across attempts with nothing but a scalar to go on.
    Both attempts' diffs must render (last 2 errors), each independently
    readable."""
    errors = [
        _wrong_gate_decomposition_error(iteration=3),
        _wrong_gate_decomposition_error(iteration=4),
    ]

    rendered = _render_errors(errors)

    assert "Attempt 3 failed" in rendered
    assert "Attempt 4 failed" in rendered
    assert rendered.count("gate counts (expected vs actual):") == 2


def test_payload_without_structural_diff_shape_falls_back_to_message_only() -> None:
    """Static/resource errors currently carry an empty payload — must not
    crash or print an empty diff block."""
    error = ErrorRecord(
        iteration=1, stage="static", error_type="SyntaxError", message="invalid syntax", payload={}
    )

    rendered = _render_errors([error])

    assert "invalid syntax" in rendered
    assert "gate counts" not in rendered


def test_gate_sequence_is_never_rendered_even_when_present_in_payload() -> None:
    """Regression test for a real, harmful bug (research.md D14): a
    position-by-position gate-sequence diff was rendered as an "expected X,
    got Y" prescription. GHZ prep via a CX chain (0->1->2) and a CX star
    (0->1, 0->2) both entangle correctly from |0..0> — same gate multiset,
    different `.data` order, neither one wrong. The positional diff flagged
    the valid topology choice as the bug and said nothing about the real
    one (extra H gates) elsewhere in the same run. A frontier model ignored
    the bad advice and fixed the circuit correctly; the local model followed
    it and stayed stuck across three iterations.

    `expected_gate_sequence`/`actual_gate_sequence` still get computed and
    attached to payload (validators/semantic.py — cheap, might be useful for
    future analysis) — this test guards against ever rendering them as a
    diff again, regardless of what the rest of `render_structural_diff`
    does.
    """
    error = ErrorRecord(
        iteration=1,
        stage="semantic",
        error_type="WrongGateDecomposition",
        message="unitária diverge da referência (fidelidade=0.5000, método=exact)",
        payload={
            "expected_n_qubits": 3,
            "actual_n_qubits": 3,
            "expected_gate_counts": {"h": 1, "cx": 2},
            "actual_gate_counts": {"h": 1, "cx": 2},
            "expected_gate_sequence": [["h", [0]], ["cx", [0, 1]], ["cx", [1, 2]]],
            "actual_gate_sequence": [["h", [0]], ["cx", [0, 1]], ["cx", [0, 2]]],
            "reversed_bit_order_matches": False,
            "direct_fidelity": 0.5,
            "reversed_bit_order_fidelity": 0.125,
        },
    )

    rendered = _render_errors([error])

    assert "gate sequence diff" not in rendered
    assert "expected" not in rendered.lower() or "qubits: expected=" in rendered
    assert "cx(1,2)" not in rendered  # no positional "expected cx(1,2)" claim
    assert "cx(0,2)" not in rendered  # no positional "actual cx(0,2)" claim
    # The counts table (the actual, unambiguous signal) is still there.
    assert "cx: 2 vs 2" in rendered
    assert "h: 1 vs 1" in rendered


def test_count_mismatch_surfaces_clearly_with_no_positional_noise() -> None:
    """The concrete case from the bug report: 3 H gates generated against 1
    expected. The count mismatch — the real, actionable signal — must
    render plainly, with nothing else in the output claiming a specific
    position is "expected" to be something else."""
    error = ErrorRecord(
        iteration=1,
        stage="semantic",
        error_type="WrongGateDecomposition",
        message="unitária diverge da referência (fidelidade=0.2500, método=exact)",
        payload={
            "expected_n_qubits": 3,
            "actual_n_qubits": 3,
            "expected_gate_counts": {"h": 1, "cx": 2},
            "actual_gate_counts": {"h": 3, "cx": 2},
            "expected_gate_sequence": [["h", [0]], ["cx", [0, 1]], ["cx", [1, 2]]],
            "actual_gate_sequence": [
                ["h", [0]],
                ["h", [1]],
                ["h", [2]],
                ["cx", [0, 1]],
                ["cx", [0, 2]],
            ],
            "reversed_bit_order_matches": False,
            "direct_fidelity": 0.25,
            "reversed_bit_order_fidelity": 0.125,
        },
    )

    rendered = _render_errors([error])

    assert "h: 1 vs 3" in rendered
    assert "cx: 2 vs 2" in rendered
    assert "gate sequence diff" not in rendered
    # "decomposition" legitimately contains "position" as a substring (it's
    # the error_type) — check for the phrase, not the bare substring.
    assert "position: expected vs actual" not in rendered.lower()


# ---------------------------------------------------------------------------
# Assertions shown to the generator from the first attempt (T090b)
# ---------------------------------------------------------------------------

import hashlib  # noqa: E402

from qcagent.nodes.generator import GENERATOR_SYSTEM_PROMPT, _build_prompt  # noqa: E402
from qcagent.state import CriticDecision, Requirement  # noqa: E402
from qcagent.validators.assertions import parse_assertions  # noqa: E402

_REQS = [
    Requirement(id="r1", kind="n_qubits", description="2 qubits", value=2),
    Requirement(id="r2", kind="property", description="produce a Bell state", value=None),
]


def test_prompts_without_assertions_are_byte_identical_to_before_the_change() -> None:
    """Golden strings captured from the generator BEFORE assertions were
    shown to it. None of the 120 regression-suite tasks declares an
    assertion, so as long as this holds, the change cannot move a single
    suite result — and a suite before/after comparison could not measure
    its risk either (it would be identical by construction). If this fails,
    every suite prompt changed and that must be a deliberate, re-measured
    decision."""
    first = _build_prompt(_REQS, {"chunks": []}, [])
    assert (
        first == "## Requirements\n\n- (n_qubits) 2 qubits = 2\n- (property) produce a Bell state"
    )

    err = ErrorRecord(iteration=1, stage="static", error_type="SyntaxError", message="boom")
    hint = CriticDecision(action="retry_generation", rationale="r", generation_hint="fix it")
    retry = _build_prompt(_REQS, {"chunks": [], "decision": hint}, [err])
    assert retry == (
        "## Requirements\n\n- (n_qubits) 2 qubits = 2\n- (property) produce a Bell state"
        "\n\n## Previous failed attempts\n\nAttempt 1 failed at stage=static, "
        "error_type=SyntaxError:\nboom\n\n## Hint for this attempt\nfix it"
    )

    assert (
        hashlib.sha256(GENERATOR_SYSTEM_PROMPT.encode()).hexdigest()
        == "cd5e21a48a9ba9f36f54fc6f98e5d0a7f3ef285156c1102d239b4b797762abc0"
    ), "the system prompt changed: every regression-suite prompt changed with it"


def test_declared_assertions_reach_the_generator_on_the_first_attempt() -> None:
    assertions = parse_assertions('PROBABILITY(|11>) ~= 0.5\nGATES_SUBSET_OF({"h", "cx"})', 2)
    prompt = _build_prompt(_REQS, {"chunks": [], "assertions": assertions}, [])

    assert "## Assertions the circuit must satisfy" in prompt
    assert "- PROBABILITY(|11>) ~= 0.5" in prompt
    assert '- GATES_SUBSET_OF({"cx", "h"})' in prompt
    # The two guards the section exists to carry.
    assert "do not replace the requirements above" in prompt
    assert "leftmost character is the highest-indexed qubit" in prompt
    # Requirements still come first: the assertions are part of the request.
    assert prompt.index("## Requirements") < prompt.index("## Assertions")
