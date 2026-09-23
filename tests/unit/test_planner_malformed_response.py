"""The planner LLM's output is not trusted to be well-formed (bug 16).

A 7B model emitting invalid JSON is a routine output, not an exceptional one.
Before this, `json.loads` raised straight out of the node, the exception left
the graph, and the run died — found on the first live suite run, where it cost
one task and would have cost the whole suite without the runner's containment.

What the status must be is the substance of these tests, not an incidental
detail. Two neighbours are wrong for opposite reasons:

* `rejected_input` says the USER's request was refused. The user wrote a
  valid prompt; our planner produced unusable output. Blaming the request for
  an upstream extraction failure is F3.
* `infrastructure_error` is excluded from the metrics denominator, so filing
  it there would hide a real weakness of the system under test in the one
  bucket nothing is counted against.

`aborted` means attempted and produced nothing usable, and stays in the
denominator.
"""

import pytest

from qcagent.llm.base import LLMResponse
from qcagent.nodes.planner import make_planner_node
from qcagent.state import AgentState

MALFORMED = [
    pytest.param(
        '{"satisfiable": true, "requirements": [{"id": "a" "kind": "n_qubits"}]}', id="json"
    ),
    pytest.param("I cannot help with that request.", id="no-json-at-all"),
    pytest.param('{"satisfiable": true}', id="missing-requirements-key"),
    pytest.param('{"satisfiable": true, "requirements": [{"id": "a"}]}', id="requirement-invalid"),
    pytest.param(
        '{"satisfiable": true, "requirements": [{"id": "a", "kind": "n_qubits",'
        ' "description": "n", "value": true}]}',
        id="value-violates-strictint",
    ),
]


class _FixedLLM:
    model_id = "stub"
    cache_dir = None

    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, *, system: str, prompt: str, seed: int, max_tokens: int = 4096):
        return LLMResponse(
            text=self.text,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            num_ctx=None,
            latency_s=0.0,
            model_id=self.model_id,
        )

    def count_tokens(self, text: str) -> int:
        return len(text)


def _run(text: str) -> dict:
    node = make_planner_node(_FixedLLM(text), max_qubits=20, seed=1)
    state: AgentState = {"task_id": "t", "spec": "build a bell state", "iteration": 0}
    return node(state)


@pytest.mark.parametrize("text", MALFORMED)
def test_malformed_planner_output_does_not_raise(text: str) -> None:
    result = _run(text)  # must not raise
    assert result["status"] == "aborted"


@pytest.mark.parametrize("text", MALFORMED)
def test_the_user_is_never_blamed_for_the_planners_output(text: str) -> None:
    assert _run(text)["status"] != "rejected_input"


@pytest.mark.parametrize("text", MALFORMED)
def test_it_is_not_hidden_outside_the_metrics_denominator(text: str) -> None:
    assert _run(text)["status"] != "infrastructure_error"


def test_the_failure_is_recorded_where_metrics_can_count_it() -> None:
    """A failure mode that appears only in a trace nobody persists is a
    failure mode nobody measures. `error_history` is what reaches the
    results file."""
    result = _run("not json")

    (error,) = result["error_history"]
    assert error.stage == "planner"
    assert error.error_type == "MalformedPlannerResponse"
    # The offending text is kept: after an unattended run, "the planner
    # produced bad JSON" without the JSON is not actionable.
    assert "not json" in error.payload["response_text"]


def test_a_well_formed_response_is_unaffected() -> None:
    result = _run(
        '{"satisfiable": true, "rejection_reason": null, "requirements": '
        '[{"id": "n", "kind": "n_qubits", "description": "qubits", "value": 2}]}'
    )
    assert result.get("status") != "aborted"
    assert [r.value for r in result["requirements"]] == [2]


# --- the critic's twin defect (bug 17) -------------------------------------
#
# Same shape, OPPOSITE correct treatment. Recorded here beside the planner's
# so the contrast is visible: what decides is what each output MEANS to the
# rest of the system, not what the exception looks like.


def test_a_malformed_critic_hint_degrades_instead_of_killing_the_run() -> None:
    """The critic's ACTION comes from `route_action`, which is deterministic
    and never consults an LLM (Principle I). Only the rationale and hint are
    model-written, so losing them costs the next attempt some quality, not
    correctness — the run must continue with the action already decided.

    The planner aborts in the same situation because without requirements
    there is nothing to generate at all.
    """
    from qcagent.nodes.critic import make_critic_node
    from qcagent.state import ErrorRecord, StaticResult

    critic = make_critic_node(_FixedLLM("this is not JSON at all"), max_iter=5, seed=1)
    state: AgentState = {
        "task_id": "t",
        "iteration": 1,
        "code": "qc = None",
        "static": StaticResult(
            parsed=True,
            executed=False,
            transpiled=False,
            error=ErrorRecord(
                iteration=1,
                stage="static",
                error_type="TranspilationFailure",
                message="boom",
            ),
        ),
    }

    result = critic(state)  # must not raise

    decision = result["decision"]
    assert decision.action == "retry_generation", "the routed action survives a bad hint"
    assert decision.generation_hint is None
    assert "ilegível" in decision.rationale
    assert result.get("status") != "infrastructure_error"
