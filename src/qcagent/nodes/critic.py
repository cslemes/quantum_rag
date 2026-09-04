"""critic node — classified error -> corrective action (FR-007). See
plan.md's "Roteamento do critic" table and data-model.md's closed error
taxonomy.

Principle I: the critic never emits a correctness verdict — `route_action`
below is pure and deterministic, driven entirely by the already-computed
StaticResult/SemanticResult/ResourceResult. The LLM is used ONLY to phrase
the human-readable rationale and the concrete hint for the next attempt,
never to decide the action itself. For the "done" and "abort" terminal
actions there is nothing to hint at, so no LLM call is made at all — this
also avoids paying for a call on the common case (a successful attempt)
across the ~5,400-run experimental matrix.
"""

import json
import re
from collections.abc import Callable
from typing import Literal

from qcagent.llm.base import BaseLLMClient, InfrastructureError
from qcagent.state import AgentState, CriticDecision, ResourceResult, SemanticResult, StaticResult

Action = Literal["retry_retrieval", "retry_generation", "optimize", "abort", "done"]

# Closed taxonomy (data-model.md) -> action. Every `error_type` the
# validators can produce must appear in exactly one of these sets, or in the
# ResourceExcess special-case below — `route_action` raises if not, so a
# taxonomy amendment that forgets to update this file fails loudly instead
# of silently misrouting.
_RETRY_RETRIEVAL_ERRORS = {"DeprecatedAPI", "HallucinatedSymbol"}
_RETRY_GENERATION_ERRORS = {
    "SyntaxError",
    "TranspilationFailure",
    "QubitIndexError",
    "MissingMeasurement",
    "ParameterBindingError",
    "EndiannessSwap",
    "WrongGateDecomposition",
    "ConceptualAlgorithmError",
}

CRITIC_SYSTEM_PROMPT = """You are the corrective-feedback stage of a quantum \
circuit synthesis pipeline. You are given the latest validation failure for a \
generated circuit and the corrective action already decided for it — you do \
NOT choose the action, it was determined deterministically from the error \
type. Your only job is to write:
  - a one-sentence rationale, suitable for a research log
  - a concrete, actionable hint for the next attempt

Respond with a single JSON object, no prose outside it:
{"rationale": string, "hint": string}

The hint's purpose depends on the action:
  - retry_retrieval: what API/version context the next retrieval query
    should look for
  - retry_generation / optimize: what to concretely change in the next
    generation attempt
"""


def _latest_error_type(
    static: StaticResult | None, semantic: SemanticResult | None, resource: ResourceResult | None
) -> str | None:
    if static is not None and static.error is not None:
        return static.error.error_type
    if semantic is not None and semantic.error is not None:
        return semantic.error.error_type
    if resource is not None and not resource.passed:
        return "ResourceExcess"
    return None


def route_action(
    static: StaticResult | None,
    semantic: SemanticResult | None,
    resource: ResourceResult | None,
    iteration: int,
    max_iter: int,
) -> tuple[Action, str | None]:
    """Deterministic routing per plan.md's critic table (FR-007). Returns
    (action, error_type). Never touches an LLM.
    """
    error_type = _latest_error_type(static, semantic, resource)
    if error_type is None:
        return "done", None
    if iteration >= max_iter:
        return "abort", error_type
    if error_type in _RETRY_RETRIEVAL_ERRORS:
        return "retry_retrieval", error_type
    if error_type == "ResourceExcess":
        return "optimize", error_type
    if error_type in _RETRY_GENERATION_ERRORS:
        return "retry_generation", error_type
    raise ValueError(f"unroutable error_type {error_type!r} — closed taxonomy violated")


def _build_hint_prompt(action: str, error_type: str | None, state: AgentState) -> str:
    error_message = ""
    for result in (state.get("static"), state.get("semantic")):
        if result is not None and result.error is not None:
            error_message = result.error.message
            break
    resource = state.get("resource")
    resource_note = ""
    if resource is not None and not resource.passed:
        resource_note = (
            f"depth_ratio={resource.depth_ratio:.2f} (limit 2.0), cx_ratio={resource.cx_ratio:.2f}"
        )
    return (
        f"action={action}\n"
        f"error_type={error_type}\n"
        f"error_message={error_message}\n"
        f"{resource_note}\n\n"
        f"code:\n{state.get('code', '')}"
    )


def _parse_hint_response(text: str) -> tuple[str, str]:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match is None:
        raise ValueError(f"critic response contains no JSON object: {text!r}")
    payload = json.loads(match.group(0))
    return payload["rationale"], payload["hint"]


def make_critic_node(
    llm: BaseLLMClient, *, max_iter: int, seed: int = 42
) -> Callable[[AgentState], dict]:
    def critic(state: AgentState) -> dict:
        action, error_type = route_action(
            state.get("static"),
            state.get("semantic"),
            state.get("resource"),
            state.get("iteration", 0),
            max_iter,
        )

        if action == "done":
            decision = CriticDecision(
                action="done", rationale="todas as camadas de verificação passaram"
            )
        elif action == "abort":
            decision = CriticDecision(
                action="abort",
                rationale=(
                    f"iteration={state.get('iteration', 0)} atingiu MAX_ITER={max_iter} "
                    f"com erro pendente ({error_type})"
                ),
            )
        else:
            prompt = _build_hint_prompt(action, error_type, state)
            try:
                response = llm.generate(
                    system=CRITIC_SYSTEM_PROMPT, prompt=prompt, seed=seed, max_tokens=512
                )
            except InfrastructureError as exc:
                # Same rule as planner.py/generator.py: an exhausted-retry
                # provider failure short-circuits the graph directly; it
                # must not be routed as if it were a generation error, which
                # would burn an iteration on infrastructure, not code.
                return {
                    "status": "infrastructure_error",
                    "trace": [{"node": "critic", "infrastructure_error": str(exc)}],
                }
            rationale, hint = _parse_hint_response(response.text)
            decision = CriticDecision(
                action=action,
                rationale=rationale,
                retrieval_hint=hint if action == "retry_retrieval" else None,
                generation_hint=hint if action in ("retry_generation", "optimize") else None,
            )

        return {
            "decision": decision,
            "trace": [{"node": "critic", "action": decision.action, "error_type": error_type}],
        }

    return critic
