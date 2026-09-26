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
across a regression-suite run (v2: up to 360 executions per run, 120 tasks
x 3 seeds against a single generator/config — see MIGRATION.md; this
replaced v1's 5,400-run experimental matrix across 3 generators x 5
conditions).
"""

import json
import re
from collections.abc import Callable
from typing import Literal

from qcagent.llm.base import BaseLLMClient, InfrastructureError
from qcagent.state import (
    AgentState,
    AssertionOutcome,
    CriticDecision,
    ErrorRecord,
    ResourceResult,
    SemanticResult,
    StaticResult,
)
from qcagent.validators.assertions import render_assertion
from qcagent.validators.static import (
    SymbolCorrection,
    missing_import_for,
    symbol_correction_for,
)

Action = Literal["retry_retrieval", "retry_generation", "optimize", "abort", "done"]

# Closed taxonomy (data-model.md) -> action. Every `error_type` the
# validators can produce must appear in exactly one of these sets, or in the
# ResourceExcess/AssertionViolated/AssertionNotEvaluable special-cases below
# — `route_action` raises if not, so a taxonomy amendment that forgets to
# update this file fails loudly instead of silently misrouting.
_RETRY_RETRIEVAL_ERRORS = {"DeprecatedAPI", "HallucinatedSymbol"}
_RETRY_GENERATION_ERRORS = {
    "SyntaxError",
    # The symbol EXISTS and was simply not imported, so retrieval cannot help
    # — no quantity of documentation adds an `import` line. Separating this
    # from HallucinatedSymbol is the whole point of the split (F14, F3): in
    # the baseline run, 112 runs spent five iterations each on
    # `retry_retrieval` for exactly this failure.
    "MissingImport",
    # An ImportError on a symbol that does not exist, where the runtime names
    # the one intended (F25). Retrieval cannot fix it: documentation does not
    # enumerate names that do not exist. The correction is derived instead.
    "UnknownSymbol",
    # The circuit was built and serialized but Qiskit's own QPY reader
    # refused it (bug 21). Regenerating may produce a circuit that survives
    # the round-trip; retrieval cannot help, and the run must not crash.
    "CircuitSerializationFailure",
    # Emitted by semantic.py when the generated circuit has a NON-FINAL
    # measurement, so there is no pure output state to compare (F11).
    # Regenerating without the mid-circuit measurement is the repair; more
    # documentation is not.
    "NonUnitaryCircuit",
    "TranspilationFailure",
    "QubitIndexError",
    "MissingMeasurement",
    "ParameterBindingError",
    "EndiannessSwap",
    "WrongGateDecomposition",
    "ConceptualAlgorithmError",
    # US3 — an assertion violation is a named conceptual error, same class
    # as WrongGateDecomposition, just against what the USER declared rather
    # than an internal reference. AssertionNotEvaluable also retries here on
    # its FIRST occurrence (regenerating might produce a circuit where the
    # referenced amplitude is no longer ~0) — only a REPEAT of the exact
    # same not-evaluable assertion on the immediately following attempt
    # short-circuits to "abort" below, checked before this set is consulted.
    "AssertionViolated",
    "AssertionNotEvaluable",
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
    static: StaticResult | None,
    assertion_results: list[AssertionOutcome] | None,
    semantic: SemanticResult | None,
    resource: ResourceResult | None,
) -> str | None:
    if static is not None and static.error is not None:
        return static.error.error_type
    # assertion_check runs right after static_check, before semantic_check
    # (plan.md's graph diagram) — checked in that same order here. A
    # violation (passed=False) takes priority over a not-evaluable one
    # (passed=None) when both are present in the same iteration: a
    # violation is concrete, actionable feedback: regenerate against it.
    if assertion_results:
        if any(o.passed is False for o in assertion_results):
            return "AssertionViolated"
        if any(o.passed is None for o in assertion_results):
            return "AssertionNotEvaluable"
    if semantic is not None and semantic.error is not None:
        return semantic.error.error_type
    if resource is not None and not resource.passed:
        return "ResourceExcess"
    return None


def _is_repeated_not_evaluable(error_history: list[ErrorRecord], iteration: int) -> bool:
    """US3 — true when the SAME assertion (matched structurally, by its
    serialized payload) was `AssertionNotEvaluable` on both this iteration
    and the immediately preceding one. `assertion_check` (graph.py) appends
    one `ErrorRecord` per not-evaluable assertion every iteration it
    occurs, so both iterations' entries are already in `error_history` by
    the time the critic runs for the current one — no separate tracking
    structure needed.
    """

    def _keys(it: int) -> set[str]:
        return {
            json.dumps(r.payload.get("assertion"), sort_keys=True)
            for r in error_history
            if r.error_type == "AssertionNotEvaluable" and r.iteration == it
        }

    current = _keys(iteration)
    if not current:
        return False
    return bool(current & _keys(iteration - 1))


def route_action(
    static: StaticResult | None,
    assertion_results: list[AssertionOutcome] | None,
    semantic: SemanticResult | None,
    resource: ResourceResult | None,
    iteration: int,
    max_iter: int,
    error_history: list[ErrorRecord],
) -> tuple[Action, str | None]:
    """Deterministic routing per plan.md's critic table (FR-007). Returns
    (action, error_type). Never touches an LLM.
    """
    error_type = _latest_error_type(static, assertion_results, semantic, resource)
    if error_type is None:
        return "done", None
    # Checked BEFORE the max_iter cutoff and before the general
    # retry_generation dispatch below (which would otherwise treat every
    # AssertionNotEvaluable, repeat or not, as just another retryable
    # error): two consecutive occurrences of the identical not-evaluable
    # assertion is evidence regenerating isn't converging on it, so this
    # stops immediately rather than waiting for MAX_ITER — see
    # data-model.md's AgentState.status="assertion_not_evaluable".
    if error_type == "AssertionNotEvaluable" and _is_repeated_not_evaluable(
        error_history, iteration
    ):
        return "abort", error_type
    if iteration >= max_iter:
        return "abort", error_type
    if error_type in _RETRY_RETRIEVAL_ERRORS:
        return "retry_retrieval", error_type
    if error_type == "ResourceExcess":
        return "optimize", error_type
    if error_type in _RETRY_GENERATION_ERRORS:
        return "retry_generation", error_type
    raise ValueError(f"unroutable error_type {error_type!r} — closed taxonomy violated")


def _missing_import_fix(state: AgentState) -> str | None:
    """The exact import line that would fix the current static error, or
    None. Reads the same classifier `static.py` used to label the error, so
    the label and the hint can never disagree about which symbol is
    missing."""
    static = state.get("static")
    if static is None or static.error is None:
        return None
    return missing_import_for(static.error.message)


def _unknown_symbol_fix(state: AgentState) -> SymbolCorrection | None:
    """Same contract as `_missing_import_fix`: the classifier that labeled
    the error is the one that names the correction."""
    static = state.get("static")
    if static is None or static.error is None:
        return None
    return symbol_correction_for(static.error.message)


def _build_hint_prompt(action: str, error_type: str | None, state: AgentState) -> str:
    error_message = ""
    for result in (state.get("static"), state.get("semantic")):
        if result is not None and result.error is not None:
            error_message = result.error.message
            break
    assertion_note = ""
    if error_type in ("AssertionViolated", "AssertionNotEvaluable"):
        # FR-012: a violated/not-evaluable assertion must be NAMED in the
        # diagnostic that reaches the repair loop, not folded into a
        # generic "semantic error" message — the whole point of US3 is
        # that this feedback is against what the USER declared.
        assertion_note = "\n".join(
            f"  [{'NOT_EVALUABLE' if o.passed is None else 'VIOLATED'}] "
            f"{render_assertion(o.assertion)} — {o.detail}"
            for o in (state.get("assertion_results") or [])
            if o.passed is not True
        )
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
        f"{assertion_note}\n"
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
        iteration = state.get("iteration", 0)
        error_history = state.get("error_history", [])
        action, error_type = route_action(
            state.get("static"),
            state.get("assertion_results"),
            state.get("semantic"),
            state.get("resource"),
            iteration,
            max_iter,
            error_history,
        )

        if action == "done":
            decision = CriticDecision(
                action="done", rationale="todas as camadas de verificação passaram"
            )
        elif action == "abort":
            if error_type == "AssertionNotEvaluable" and _is_repeated_not_evaluable(
                error_history, iteration
            ):
                rationale = (
                    "a mesma asserção voltou 'não avaliável' em duas tentativas "
                    "consecutivas — regenerar não convergiu, encerrado antes de "
                    "MAX_ITER (ver AgentState.status='assertion_not_evaluable')"
                )
            else:
                rationale = (
                    f"iteration={iteration} atingiu MAX_ITER={max_iter} com erro pendente "
                    f"({error_type})"
                )
            decision = CriticDecision(action="abort", rationale=rationale)
        elif error_type == "MissingImport" and (fix := _missing_import_fix(state)) is not None:
            # The one repair this system knows EXACTLY, with no model in the
            # loop: the symbol resolved to a real module, so the fix is a
            # specific line of code. Asking an LLM to phrase a hint we can
            # derive deterministically would add a call, a failure mode and
            # a chance of saying something wrong, for nothing.
            decision = CriticDecision(
                action=action,
                rationale=f"símbolo existe mas não foi importado — falta `{fix}`",
                generation_hint=(
                    f"The code uses a symbol it never imports. Add exactly this line "
                    f"at the top of the code:\n\n    {fix}\n\n"
                    "Keep the rest of the circuit as it is — the gates themselves were "
                    "not what failed. Include EVERY import the code needs."
                ),
            )
        elif error_type == "UnknownSymbol" and (fix := _unknown_symbol_fix(state)) is not None:
            # Negative knowledge, derived from the runtime (F25): no retrieved
            # page could say this, and an LLM paraphrase could only add error.
            decision = CriticDecision(
                action=action,
                rationale=f"símbolo inexistente — {fix.reason}",
                generation_hint=(
                    f"{fix.reason}. Replace that import with exactly this line:\n\n"
                    f"    {fix.import_line}\n\n"
                    f"and use `{fix.replacement}` wherever the code used `{fix.symbol}`. "
                    "Keep the rest of the circuit as it is — the gates themselves were "
                    "not what failed. Include EVERY import the code needs."
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
            try:
                rationale, hint = _parse_hint_response(response.text)
            except (ValueError, KeyError, TypeError) as exc:
                # Bug 17. Unlike the planner's equivalent (which aborts,
                # because without requirements there is nothing to generate),
                # a malformed hint here DEGRADES: `action` above came from
                # `route_action`, which is deterministic and never consults
                # an LLM (Principle I). Losing the hint costs the next
                # attempt some quality, not correctness, so the run
                # continues with the action it already decided on.
                rationale = f"crítico devolveu resposta ilegível ({type(exc).__name__}); "
                rationale += "seguindo com a ação roteada, sem dica"
                hint = None
            decision = CriticDecision(
                action=action,
                rationale=rationale,
                retrieval_hint=hint if action == "retry_retrieval" else None,
                generation_hint=hint if action in ("retry_generation", "optimize") else None,
            )

        return {
            "decision": decision,
            # rationale and both hints are persisted (RunRecord.trace, F27):
            # without them a retry_retrieval that failed cannot be told apart
            # from one that asked for the wrong thing.
            "trace": [
                {
                    "node": "critic",
                    "action": decision.action,
                    "error_type": error_type,
                    "rationale": decision.rationale,
                    "retrieval_hint": decision.retrieval_hint,
                    "generation_hint": decision.generation_hint,
                }
            ],
        }

    return critic
