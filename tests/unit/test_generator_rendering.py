"""How failed attempts reach the generator, and how the structural diff is
formatted for the maintainer.

T118 (the information rule applied to the generator): a failure computed by
COMPARING with the reference is shown to the generator only as a neutral
note plus what its own circuit did — never the reference's gate counts, the
fidelity, the reversed-bit-order check or the reference-derived error type.
Before T118 the generator was shown all of them; every arm up to R2 ran that
way (F31 correction, F32).

`render_structural_diff` still exists and is tested here, but as the
maintainer's by-hand view (`bench/run_single.py`), not the generator's.
"""

from qcagent.nodes.generator import _render_errors, render_structural_diff
from qcagent.state import ErrorRecord

_ARTIFACT = (
    "qubits: 2\ngate counts: {'x': 2}\ndepth: 1\n"
    "output distribution, most likely states (qubit 0 rightmost): |11>: 1.000"
)


def _wrong_gate_decomposition_error(iteration: int, *, artifact: bool = True) -> ErrorRecord:
    payload = {
        "expected_n_qubits": 2,
        "actual_n_qubits": 2,
        "expected_gate_counts": {"h": 1, "cx": 1},
        "actual_gate_counts": {"x": 2},
        "reversed_bit_order_matches": False,
        "direct_fidelity": 0.3536,
        "reversed_bit_order_fidelity": 0.3536,
    }
    if artifact:
        payload["artifact"] = _ARTIFACT
    return ErrorRecord(
        iteration=iteration,
        stage="semantic",
        error_type="WrongGateDecomposition",
        message="unitária diverge da referência (fidelidade=0.3536, método=exact)",
        payload=payload,
    )


# --- what the generator sees (T118) ------------------------------------------


def test_no_reference_derived_information_reaches_the_generator() -> None:
    rendered = _render_errors([_wrong_gate_decomposition_error(iteration=1)])

    assert "fidelidade" not in rendered and "fidelity" not in rendered.lower()
    assert "expected" not in rendered.lower()
    assert "vs" not in rendered  # no expected-vs-actual table
    assert "reversed-bit-order" not in rendered
    assert "WrongGateDecomposition" not in rendered


def test_the_generator_sees_what_its_own_circuit_did() -> None:
    """Substitution, not removal: the distribution says what the circuit did;
    the fidelity only said it was wrong."""
    rendered = _render_errors([_wrong_gate_decomposition_error(iteration=1)])

    assert "Attempt 1 failed: the circuit ran, but its output does not do what the task asks" in (
        rendered
    )
    assert "What that circuit did:" in rendered
    assert "|11>: 1.000" in rendered
    assert "gate counts: {'x': 2}" in rendered


def test_both_recent_attempts_are_described_independently() -> None:
    rendered = _render_errors(
        [_wrong_gate_decomposition_error(iteration=3), _wrong_gate_decomposition_error(iteration=4)]
    )
    assert "Attempt 3 failed" in rendered and "Attempt 4 failed" in rendered
    assert rendered.count("What that circuit did:") == 2


def test_a_failure_recorded_before_t118_still_hides_the_reference() -> None:
    """An error without an attached artifact (e.g. read back from an older
    run) still shows no reference data — just the neutral note."""
    rendered = _render_errors([_wrong_gate_decomposition_error(iteration=1, artifact=False)])
    assert "functional check failed" in rendered
    assert "vs" not in rendered and "fidelidade" not in rendered


def test_static_errors_keep_their_exact_message() -> None:
    """A static error comes from executing the user's own code, not from the
    reference — fair under the rule, and the most actionable thing there is."""
    error = ErrorRecord(
        iteration=1, stage="static", error_type="SyntaxError", message="invalid syntax", payload={}
    )
    rendered = _render_errors([error])
    assert "error_type=SyntaxError" in rendered and "invalid syntax" in rendered


def test_resource_ratios_are_reference_derived_too() -> None:
    """depth_ratio/cx_ratio are relative to the reference circuit."""
    error = ErrorRecord(
        iteration=2,
        stage="resource",
        error_type="ResourceExcess",
        message="depth_ratio=3.10, cx_ratio=2.50",
        payload={},
    )
    rendered = _render_errors([error])
    assert "depth_ratio" not in rendered and "3.10" not in rendered
    assert "resource budget" in rendered


# --- the maintainer's view: render_structural_diff ---------------------------


def test_structural_diff_is_readable_text_not_a_dict_dump() -> None:
    rendered = render_structural_diff(_wrong_gate_decomposition_error(1).payload)
    assert rendered is not None
    assert "{'expected_gate_counts'" not in rendered
    assert "qubits: expected=2, actual=2" in rendered
    assert "h: 1 vs 0" in rendered and "cx: 1 vs 0" in rendered and "x: 0 vs 2" in rendered
    assert "reversed-bit-order check: also failed" in rendered


def test_gate_sequence_is_never_rendered_even_when_present_in_payload() -> None:
    """research.md D14: a positional "expected X, got Y" gate-sequence diff
    flags valid topology choices (CX chain vs CX star) as bugs. Guarded on
    the formatter, which still serves the maintainer's inspection view."""
    rendered = render_structural_diff(
        {
            "expected_n_qubits": 3,
            "actual_n_qubits": 3,
            "expected_gate_counts": {"h": 1, "cx": 2},
            "actual_gate_counts": {"h": 3, "cx": 2},
            "expected_gate_sequence": [["h", [0]], ["cx", [0, 1]], ["cx", [1, 2]]],
            "actual_gate_sequence": [["h", [0]], ["cx", [0, 1]], ["cx", [0, 2]]],
            "reversed_bit_order_matches": False,
            "reversed_bit_order_fidelity": 0.125,
        }
    )
    assert rendered is not None
    assert "gate sequence diff" not in rendered
    assert "cx(1,2)" not in rendered and "cx(0,2)" not in rendered
    assert "h: 1 vs 3" in rendered and "cx: 2 vs 2" in rendered


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


# ---------------------------------------------------------------------------
# Edit-based repair (T090d)
# ---------------------------------------------------------------------------


def test_retry_shows_previous_code_with_an_edit_instruction() -> None:
    err = _wrong_gate_decomposition_error(iteration=1)
    prompt = _build_prompt(_REQS, {"chunks": [], "code": "qc = make()"}, [err])

    assert "## Code of the previous attempt" in prompt
    assert "qc = make()" in prompt
    assert "Do not rewrite it from scratch" in prompt
    # After the errors, before any critic hint.
    assert prompt.index("## Previous failed attempts") < prompt.index("## Code of the previous")


def test_resource_excess_tells_the_generator_the_circuit_is_correct() -> None:
    err = ErrorRecord(
        iteration=2,
        stage="resource",
        error_type="ResourceExcess",
        message="depth 9x",
        payload={"artifact": _ARTIFACT},
    )
    prompt = _build_prompt(_REQS, {"chunks": [], "code": "qc = big()"}, [err])

    assert "functionally correct" in prompt
    assert "WITHOUT changing what it computes" in prompt


def test_first_attempt_prompt_never_carries_code() -> None:
    """F16 control: attempt 1 has nothing to edit, so its prompt cannot move."""
    assert "previous attempt" not in _build_prompt(_REQS, {"chunks": [], "code": "x"}, [])
