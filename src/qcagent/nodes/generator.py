"""generator node — requirements + chunks + last 2 errors -> code. See
plan.md's node contract table and data-model.md's "Nota de projeto" (only
the last 2 errors go in context, not the full history — otherwise the
prompt grows linearly with iterations and cost explodes in condition C5).
"""

import re
from collections.abc import Callable

from qcagent.llm.base import BaseLLMClient, InfrastructureError
from qcagent.retrieval.hybrid import split_by_register
from qcagent.state import AgentState, Assertion, ErrorRecord, Requirement
from qcagent.validators.assertions import render_assertion

GENERATOR_SYSTEM_PROMPT = """You are the code-generation stage of a quantum \
circuit synthesis pipeline. Given a list of verifiable requirements, retrieved \
documentation context, and (if present) the most recent validation errors, \
produce Qiskit 1.x Python code that builds the requested circuit.

Rules:
  - Assign the resulting QuantumCircuit to a variable named exactly `qc`.
  - Use only current, non-deprecated Qiskit 1.x API. Any chunk marked
    "[OBSOLETO — NÃO USAR]" in the context must never appear in your code —
    use the indicated replacement instead.
  - Respond with a single fenced Python code block and nothing else.
"""


def _render_requirements(requirements: list[Requirement]) -> str:
    lines = [
        f"- ({r.kind}) {r.description}" + (f" = {r.value!r}" if r.value is not None else "")
        for r in requirements
    ]
    return "\n".join(lines)


def render_structural_diff(payload: dict) -> str | None:
    """Renders the structural diff validators/semantic.py attaches to a
    semantic ErrorRecord's payload (see `check_with_endianness`'s
    `_structural_diff`) as readable lines, not a raw dict dump. Returns
    None for a payload without this shape (e.g. static/resource errors,
    which currently carry an empty payload) so the caller falls back to
    the plain message alone.

    A bare fidelity scalar tells the generator it's wrong but not what to
    change; the gate-count table is the concrete diff a retry can act on.

    Deliberately does NOT render a position-by-position gate-sequence diff.
    An earlier version did (see git/session history and research.md D14's
    note on this) — it compared `expected_gate_sequence[i]` against
    `actual_gate_sequence[i]` and phrased mismatches as "expected X, got Y".
    That assumes a canonical gate ordering that doesn't exist: two
    circuits can have identical gate multisets and still be different
    orderings of an equally valid decomposition (e.g. GHZ prep via a CX
    chain, 0->1->2, vs a CX star, 0->1 and 0->2, both entangle correctly
    from |0..0>, and Qiskit's `.data` order is just "however the author
    happened to write it", not a spec). The positional diff would flag the
    star/chain divergence as if it were a bug and stay silent about
    unrelated real bugs, actively pointing a retry at the wrong thing. A
    generator that trusts a wrong "expected X" over its own read of the
    code is worse off than one given no positional diff at all.

    Public (not `_`-prefixed): bench/run_single.py reuses this directly so
    a by-hand inspection shows the exact same rendering the model receives,
    instead of a second formatter drifting out of sync with this one.
    """
    if "expected_gate_counts" not in payload:
        return None

    lines = [
        f"  qubits: expected={payload['expected_n_qubits']}, actual={payload['actual_n_qubits']}"
    ]

    expected_gates: dict = payload["expected_gate_counts"]
    actual_gates: dict = payload["actual_gate_counts"]
    gate_names = sorted(set(expected_gates) | set(actual_gates))
    if gate_names:
        lines.append("  gate counts (expected vs actual):")
        lines.extend(
            f"    {name}: {expected_gates.get(name, 0)} vs {actual_gates.get(name, 0)}"
            for name in gate_names
        )

    if payload.get("reversed_bit_order_matches"):
        lines.append(
            "  reversed-bit-order check: MATCHES — this looks like an endianness "
            "swap, not a logic error"
        )
    else:
        reversed_fidelity = payload.get("reversed_bit_order_fidelity")
        suffix = f" (fidelity={reversed_fidelity:.4f})" if reversed_fidelity is not None else ""
        lines.append(f"  reversed-bit-order check: also failed{suffix}")

    return "\n".join(lines)


def _render_errors(errors: list[ErrorRecord]) -> str:
    if not errors:
        return ""
    blocks = []
    for e in errors:
        block = (
            f"Attempt {e.iteration} failed at stage={e.stage}, "
            f"error_type={e.error_type}:\n{e.message}"
        )
        diff = render_structural_diff(e.payload) if e.payload else None
        if diff:
            block += f"\n{diff}"
        blocks.append(block)
    return "## Previous failed attempts\n\n" + "\n\n".join(blocks)


def _extract_code(text: str) -> str:
    """Pulls the content of a fenced code block. Falls back to the raw text
    if the model didn't fence it, since some prompts still leak bare code."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return match.group(1).strip() if match is not None else text.strip()


def _render_assertions(assertions: list[Assertion]) -> str:
    """The user's assertions, shown from the FIRST attempt. Before this the
    generator saw them only after one was violated, guessing at what the
    user wanted while the exact specification sat unused. This is not
    oracle leakage: it is the user restating their own request.

    Two things the text below deliberately does:
      - states the ordering convention, because `PROBABILITY(|01>)` read
        the other way round is a different basis state, and a generator
        that guesses the convention wrong fails every assertion it can see;
      - says the assertions are PART of the request, not all of it. The
        risk of showing them is a circuit that satisfies what was asserted
        and ignores the rest; that risk is to be measured against the
        reference oracle, not assumed away (see tasks.md T090b).

    Only present when assertions were declared, so every prompt without
    them is byte-identical to before — pinned by
    tests/unit/test_generator_rendering.py.
    """
    lines = "\n".join(f"- {render_assertion(a)}" for a in assertions)
    return (
        "## Assertions the circuit must satisfy\n"
        "Declared by the user. They state SOME properties the finished circuit must "
        "have; they do not replace the requirements above, which still describe the "
        "whole circuit to build.\n"
        "Convention: in every ket and Pauli string the leftmost character is the "
        "highest-indexed qubit and the rightmost is qubit 0 (Qiskit's own ordering). "
        "MEASURES([q, ...]) is the exception: its bitstring lists those qubits in the "
        "order written. Final measurements are ignored when these are checked.\n"
        f"{lines}"
    )


def _build_prompt(
    requirements: list[Requirement], state: AgentState, last_errors: list[ErrorRecord]
) -> str:
    bundle = split_by_register(state.get("chunks", []))
    sections = [
        "## Requirements",
        _render_requirements(requirements),
    ]
    assertions = state.get("assertions") or []
    if assertions:
        sections.append(_render_assertions(assertions))
    context = bundle.to_prompt_context()
    if context:
        sections.append("## Retrieved context")
        sections.append(context)
    error_section = _render_errors(last_errors)
    if error_section:
        sections.append(error_section)
    decision = state.get("decision")
    if decision is not None and decision.generation_hint:
        sections.append(f"## Hint for this attempt\n{decision.generation_hint}")
    return "\n\n".join(sections)


def make_generator_node(llm: BaseLLMClient, *, seed: int = 42) -> Callable[[AgentState], dict]:
    def generator(state: AgentState) -> dict:
        requirements = state.get("requirements", [])
        error_history = state.get("error_history", [])
        last_errors = error_history[-2:]  # only the 2 most recent — see module docstring

        prompt = _build_prompt(requirements, state, last_errors)
        try:
            response = llm.generate(
                system=GENERATOR_SYSTEM_PROMPT, prompt=prompt, seed=seed, max_tokens=4096
            )
        except InfrastructureError as exc:
            # Same rule as planner.py: never route this through the critic —
            # it isn't an error_type of generated code, and no generation
            # attempt actually happened, so `iteration` is left untouched.
            return {
                "status": "infrastructure_error",
                "trace": [{"node": "generator", "infrastructure_error": str(exc)}],
            }

        code = _extract_code(response.text)
        iteration = state.get("iteration", 0) + 1

        return {
            "code": code,
            "iteration": iteration,
            # data-model.md: static/semantic/resource/decision hold ONLY the
            # current attempt, never accumulate. New code invalidates every
            # prior verdict, so a fresh attempt must start with all four
            # cleared — otherwise a stale value from an earlier iteration
            # (e.g. a semantic verdict from iteration N-1) survives into an
            # attempt that never got that far (e.g. failed static_check on
            # iteration N), which is exactly what nothing was clearing
            # before this fix.
            "static": None,
            "semantic": None,
            "resource": None,
            "decision": None,
            # Added later than the four above, and missed when they were:
            # without these, attempt N's assertion/requirement verdicts
            # survived into attempt N+1 whenever N+1 never reached
            # assertion_check. End to end (T092) that produced a report
            # saying "FUNCTIONAL CORRECTNESS: VERIFIED" about code that had
            # failed to execute, next to status="failed_static".
            "assertion_results": None,
            "requirement_results": None,
            "trace": [{"node": "generator", "iteration": iteration}],
        }

    return generator
