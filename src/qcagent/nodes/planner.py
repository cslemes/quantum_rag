"""planner node — natural-language spec -> list[Requirement], or an upfront
rejection (FR-030, FR-031). See plan.md's node contract table and T024b.
"""

import json
import re
from collections.abc import Callable
from typing import NamedTuple

from qcagent.llm.base import BaseLLMClient, InfrastructureError
from qcagent.state import (
    AgentState,
    Assertion,
    ErrorRecord,
    QubitCountCorrection,
    Requirement,
)
from qcagent.validators.assertions import (
    AssertionParseError,
    declared_register_widths,
    minimum_register_width,
    parse_assertions,
    width_statements,
)

PLANNER_SYSTEM_PROMPT = """You are the requirements-extraction stage of a quantum \
circuit synthesis pipeline. Given a natural-language circuit description, extract \
a list of verifiable requirements and judge whether the description is \
satisfiable.

Respond with a single JSON object, no prose outside it:

{
  "satisfiable": true | false,
  "rejection_reason": string | null,
  "requirements": [
    {"id": string, "kind": "n_qubits" | "gate_set" | "property" | "resource" | "output_format",
     "description": string, "value": string | integer | array of string | null}
  ]
}

`rejection_reason` is required (non-null) whenever satisfiable=false.

Set satisfiable=false ONLY for cases identifiable from the description itself,
without attempting generation:
  - a missing entity the description depends on (e.g. it references a named
    circuit, dataset, or oracle that is never defined)
  - mutually contradictory constraints (e.g. requires both an odd and an even
    number of qubits, or excludes a gate that the requested algorithm cannot
    be built without)

Do NOT reject for ambiguity that a generate-and-retry loop could plausibly
resolve — that is handled elsewhere, not here. Always extract requirements
even when satisfiable=false, using your best reading of the description.

If the description specifies or clearly implies a qubit count, ALWAYS emit a
requirement with kind="n_qubits" and an integer value. A downstream
deterministic check depends on this field — never omit it when a count is
determinable from the text.
"""


def _parse_planner_response(text: str) -> tuple[bool, str | None, list[Requirement]]:
    """Extracts (satisfiable, rejection_reason, requirements) from the
    planner LLM's raw text. Tolerates a JSON object wrapped in prose or a
    fenced code block, since models routinely do that despite instructions.
    """
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError(f"planner response contains no JSON object: {text!r}")
    payload = json.loads(match.group(0))
    requirements = [Requirement.model_validate(r) for r in payload["requirements"]]
    return bool(payload["satisfiable"]), payload.get("rejection_reason"), requirements


def _extracted_n_qubits(requirements: list[Requirement]) -> int | None:
    for req in requirements:
        if req.kind == "n_qubits" and isinstance(req.value, int):
            return req.value
    return None


def check_capacity(requirements: list[Requirement], max_qubits: int) -> str | None:
    """T024b — FR-031. The qubit ceiling is a hard configured limit, not a
    judgment call, so it's checked here deterministically rather than left to
    the planner LLM's own `satisfiable` flag. Returns a rejection reason, or
    None when within capacity (including when no n_qubits requirement was
    extracted at all — absence isn't excess).
    """
    n_qubits = _extracted_n_qubits(requirements)
    if n_qubits is not None and n_qubits > max_qubits:
        return (
            f"requisito n_qubits={n_qubits} excede o teto de simulação configurado ({max_qubits})"
        )
    return None


class AssertionCheck(NamedTuple):
    assertions: list[Assertion]
    # The planner's requirements, with an extracted n_qubits CORRECTED when
    # the user's own assertions state a different register width.
    requirements: list[Requirement]
    rejection: str | None
    # Set only when two or more agreeing assertions overruled the planner.
    n_qubits_correction: QubitCountCorrection | None


def check_assertions(
    assertions_text: str | None, requirements: list[Requirement]
) -> AssertionCheck:
    """T090 — FR-013's parse-time refusal happens HERE, before any
    generation, reusing `status="rejected_input"` (T024b).

    The register width comes from the USER'S OWN ASSERTIONS whenever they
    state one, not from the planner. An earlier version validated every
    assertion against the n_qubits the LLM extracted, so a planner that read
    a 2-qubit Bell task as 3 qubits refused a correct `PROBABILITY(|11>)` as
    "malformed" — rejecting the user's direct statement because a model
    misread the prompt, which inverts the source of truth and blames the
    user for an upstream extraction error (F3, F9). So:

      - assertions that disagree among themselves about the width: refused.
        That one IS a user error.
      - TWO OR MORE assertions state the same width and the planner
        extracted a different one: the assertions win and the extracted
        n_qubits requirement is corrected to match. Agreeing statements are
        strong evidence the extraction was wrong. The correction goes to the
        guarantee report, not only the trace. Left uncorrected, the wrong
        count would steer the generator (it reads the requirements) and
        then veto a correct circuit through T091.
      - ONE assertion states a width the planner contradicts: refused, and
        the refusal asks. That is genuine ambiguity between two sources —
        a misread description, or a typo in the one ket (`|0>` meant as two
        qubits) — with nothing to break the tie. Correcting silently would
        let a one-character typo change the task's width, and a report line
        after the fact would inform the one reader least likely to reread.
      - assertions name only qubit indices (QUBIT, MEASURES([...])) and
        state no width: the planner's count is the only width available. If
        it can't hold the highest index named, the refusal says exactly
        that, and asks for a full-register assertion — it does not call the
        assertion malformed.
    """
    if not assertions_text or not assertions_text.strip():
        return AssertionCheck([], requirements, None, None)

    extracted = _extracted_n_qubits(requirements)
    declared = declared_register_widths(assertions_text)
    if len(declared) > 1:
        return AssertionCheck(
            [],
            requirements,
            "your assertions disagree among themselves about the number of qubits: "
            f"they are written for {sorted(declared)} qubits",
            None,
        )

    if declared:
        (n_qubits,) = declared
        width_source = "your own assertions"
        statements = width_statements(assertions_text)
        if extracted is not None and extracted != n_qubits and len(statements) == 1:
            (line, _) = statements[0]
            return AssertionCheck(
                [],
                requirements,
                f"ambiguous qubit count: the description was read as {extracted} qubits, "
                f"but your only assertion that states a width, `{line}`, is written for "
                f"{n_qubits}. With one statement on each side there is nothing to decide "
                f"between them. If the circuit should have {n_qubits} qubits, say so in the "
                "description or add another assertion over the whole register; if it "
                f"should have {extracted}, correct the assertion.",
                None,
            )
    else:
        lowest = minimum_register_width(assertions_text)
        if lowest and (extracted is None or extracted < lowest):
            read_as = (
                f"was read as {extracted} qubits"
                if extracted is not None
                else "gave no qubit count that could be read"
            )
            return AssertionCheck(
                [],
                requirements,
                f"your assertions name qubit {lowest - 1}, but none of them states the "
                f"register width and the description {read_as} — add an assertion "
                'over the whole register (e.g. a PROBABILITY or MEASURES == "..." '
                "line) so the width comes from you rather than from the extraction",
                None,
            )
        # Only GATES_SUBSET_OF (width-free) or index-only forms that fit.
        n_qubits = extracted if extracted is not None else 0
        width_source = "the description"

    try:
        assertions = parse_assertions(assertions_text, n_qubits)
    except AssertionParseError as exc:
        return AssertionCheck(
            [],
            requirements,
            f"malformed assertion (register width {n_qubits}, from {width_source}): {exc}",
            None,
        )

    if not declared or extracted is None or extracted == n_qubits:
        return AssertionCheck(assertions, requirements, None, None)

    corrected = [
        r.model_copy(
            update={
                "value": n_qubits,
                "description": (
                    f"{r.description} [corrected: the planner read {extracted} qubits; "
                    f"the user's own assertions are written for {n_qubits}]"
                ),
            }
        )
        if r.kind == "n_qubits" and isinstance(r.value, int) and not isinstance(r.value, bool)
        else r
        for r in requirements
    ]
    return AssertionCheck(
        assertions,
        corrected,
        None,
        QubitCountCorrection(
            planner_n_qubits=extracted,
            assertions_n_qubits=n_qubits,
            supporting_assertions=len(width_statements(assertions_text)),
        ),
    )


def make_planner_node(
    llm: BaseLLMClient, *, max_qubits: int = 20, seed: int = 42
) -> Callable[[AgentState], dict]:
    def planner(state: AgentState) -> dict:
        try:
            response = llm.generate(
                system=PLANNER_SYSTEM_PROMPT, prompt=state["spec"], seed=seed, max_tokens=2048
            )
        except InfrastructureError as exc:
            # Provider retries already exhausted inside llm/base.py. This is
            # not an error_type of generated code, so it must never reach
            # the critic — routing.py short-circuits straight to END on
            # status="infrastructure_error" (spec edge case, T012b).
            return {
                "status": "infrastructure_error",
                "trace": [{"node": "planner", "infrastructure_error": str(exc)}],
            }

        try:
            satisfiable, rejection_reason, requirements = _parse_planner_response(response.text)
        except (ValueError, KeyError, TypeError) as exc:
            # A 7B model emitting invalid JSON is a routine output, not an
            # exceptional one, and before this it escaped as an unhandled
            # exception that took the whole run down (found on the first live
            # suite run: `json.decoder.JSONDecodeError` out of the planner).
            #
            # `aborted`, deliberately, and not either neighbour:
            #   - NOT `rejected_input`: that says the USER's request was
            #     refused. The user wrote a valid prompt; our planner LLM
            #     produced unusable output. Blaming the request for an
            #     upstream extraction failure is F3, the same mistake the
            #     qubit-count rule already exists to prevent.
            #   - NOT `infrastructure_error`: the provider answered fine. That
            #     status is excluded from the metrics denominator, so filing
            #     this there would hide a real weakness of the system under
            #     test in the one bucket nothing is counted against.
            # `aborted` means attempted and produced nothing usable, which is
            # exactly what happened. It stays in the denominator.
            #
            # `ValueError` covers `json.JSONDecodeError` (a subclass) and the
            # "no JSON object" raise, plus pydantic's ValidationError for a
            # requirement that violates the declared contract.
            return {
                "status": "aborted",
                "error_history": [
                    ErrorRecord(
                        iteration=0,
                        stage="planner",
                        error_type="MalformedPlannerResponse",
                        message=f"{type(exc).__name__}: {exc}",
                        payload={"response_text": response.text[:2000]},
                    )
                ],
                "trace": [{"node": "planner", "unparseable_response": str(exc)}],
            }
        trace_entry: dict[str, object] = {
            "node": "planner",
            "requirements": [r.model_dump() for r in requirements],
        }

        if not satisfiable:
            return {
                "requirements": requirements,
                "status": "rejected_input",
                "trace": [{**trace_entry, "rejected": True, "reason": rejection_reason}],
            }

        # Assertions are resolved BEFORE the capacity check, because they can
        # now change the qubit count: when the user's assertions state a
        # width, the capacity ceiling must apply to that width, not to the
        # count an LLM extracted.
        check = check_assertions(state.get("assertions_text"), requirements)
        if check.rejection is not None:
            return {
                "requirements": requirements,
                "status": "rejected_input",
                "trace": [{**trace_entry, "rejected": True, "reason": check.rejection}],
            }
        requirements = check.requirements

        capacity_rejection = check_capacity(requirements, max_qubits)
        if capacity_rejection is not None:
            return {
                "requirements": requirements,
                "status": "rejected_input",
                "trace": [{**trace_entry, "rejected": True, "reason": capacity_rejection}],
            }

        if check.n_qubits_correction is not None:
            trace_entry["n_qubits_corrected"] = check.n_qubits_correction.model_dump()
        return {
            "requirements": requirements,
            "assertions": check.assertions,
            "n_qubits_correction": check.n_qubits_correction,
            "status": "running",
            "trace": [{**trace_entry, "rejected": False}],
        }

    return planner
