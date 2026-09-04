"""planner node — natural-language spec -> list[Requirement], or an upfront
rejection (FR-030, FR-031). See plan.md's node contract table and T024b.
"""

import json
import re
from collections.abc import Callable

from qcagent.llm.base import BaseLLMClient, InfrastructureError
from qcagent.state import AgentState, Requirement

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

        satisfiable, rejection_reason, requirements = _parse_planner_response(response.text)
        capacity_rejection = check_capacity(requirements, max_qubits)

        trace_entry = {"node": "planner", "requirements": [r.model_dump() for r in requirements]}

        if not satisfiable:
            return {
                "requirements": requirements,
                "status": "rejected_input",
                "trace": [{**trace_entry, "rejected": True, "reason": rejection_reason}],
            }
        if capacity_rejection is not None:
            return {
                "requirements": requirements,
                "status": "rejected_input",
                "trace": [{**trace_entry, "rejected": True, "reason": capacity_rejection}],
            }
        return {
            "requirements": requirements,
            "status": "running",
            "trace": [{**trace_entry, "rejected": False}],
        }

    return planner
