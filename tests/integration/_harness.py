"""Shared harness for the US3/US4 end-to-end tests (T092, T098).

Everything is the REAL graph — real planner/generator/critic nodes, real
sandboxed `static_check` over a `WorkerPool`, real `assertion_check`, real
routing, real `finalize` — with only the LLMs scripted. The scripted clients
RECORD every prompt they receive, because several US3/US4 guarantees are
about what reaches the model (FR-012: a violated assertion is named in the
diagnostic), not only about the final state.

Not a conftest.py: tests/integration/test_us1_flow.py and test_us2_flow.py
define their own fixtures and helpers, and a conftest would silently apply
to them too.
"""

import json
from collections.abc import Callable
from pathlib import Path

from qiskit import QuantumCircuit

from qcagent.graph import (
    build_graph,
    make_assertion_check_node,
    make_resource_check_node,
    make_semantic_check_node,
    make_static_check_node,
    recursion_limit_for,
)
from qcagent.llm.base import BaseLLMClient, LLMResponse
from qcagent.nodes.critic import make_critic_node
from qcagent.nodes.generator import make_generator_node
from qcagent.nodes.planner import make_planner_node
from qcagent.report import GuaranteeReport, render_guarantee_report
from qcagent.state import AgentState
from qcagent.validators.sandbox import WorkerPool

# -- Generated-code fixtures -------------------------------------------------

_HEADER = "from qiskit import QuantumCircuit\n"

BELL_CODE = _HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\n"
# What real generated code very often looks like: the same circuit, measured.
BELL_MEASURED_CODE = BELL_CODE + "qc.measure_all()\n"
# Phi-minus: identical |00>/|11> probabilities to Bell, different unitary.
PHI_MINUS_CODE = _HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\nqc.z(0)\nqc.cx(0, 1)\n"
# Executes, but never entangles: P(|11>) = 0.
BROKEN_BELL_CODE = _HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\n"
# Identity on 2 qubits: amplitude of |11> is exactly 0, so PHASE_DIFF against
# it is undefined — the tri-state "not evaluable" case, for real.
IDENTITY_CODE = _HEADER + "qc = QuantumCircuit(2)\n"
# Never defines `qc` -> static_check fails (SyntaxError by static.py's fallback).
NON_EXECUTING_CODE = _HEADER + "x = QuantumCircuit(2)\nx.h(0)\n"
# Bell-like, but on the wrong register width: 3 qubits for a 2-qubit request.
THREE_QUBIT_CODE = _HEADER + "qc = QuantumCircuit(3)\nqc.h(0)\nqc.cx(0, 1)\n"
# CX is self-inverse, so 5 CXs == 1 CX: unitarily a Bell circuit, but at
# opt_level=0 (no cancellation) depth_ratio=3.0 against the Bell reference,
# past the default max_depth_ratio=2.0. Same construction as test_us1_flow.py.
HEAVY_BELL_CODE = _HEADER + "qc = QuantumCircuit(2)\nqc.h(0)\n" + "qc.cx(0, 1)\n" * 5

CRITIC_HINT_JSON = json.dumps({"rationale": "fix and retry", "hint": "try again carefully"})


def fenced(code: str) -> str:
    return f"```python\n{code}```"


def planner_json(n_qubits: int | None = 2, *, extra: tuple[dict, ...] = ()) -> str:
    requirements: list[dict] = []
    if n_qubits is not None:
        requirements.append(
            {"id": "r1", "kind": "n_qubits", "description": f"{n_qubits} qubits", "value": n_qubits}
        )
    requirements.append(
        {"id": "r2", "kind": "property", "description": "the requested circuit", "value": None}
    )
    requirements.extend(extra)
    return json.dumps({"satisfiable": True, "rejection_reason": None, "requirements": requirements})


# -- Scripted, prompt-recording LLM -------------------------------------------


class RecordingLLMClient(BaseLLMClient):
    """One scripted response per non-cached call, in order; every prompt is
    recorded. A unique `cache_dir` per test keeps the disk cache from
    replaying an earlier test's answer."""

    model_id = "scripted-recording"

    def __init__(self, responses: list[str], cache_dir: Path) -> None:
        self.responses = responses
        self.prompts: list[str] = []
        self.cache_dir = cache_dir

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        if self.calls >= len(self.responses):
            raise AssertionError(
                f"{self.model_id} called {self.calls + 1} times but only "
                f"{len(self.responses)} responses were scripted — prompt was:\n{prompt}"
            )
        text = self.responses[self.calls]
        self.prompts.append(prompt)
        return LLMResponse(
            text=text,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_s=0.001,
            model_id=self.model_id,
        )


# -- Graph construction ---------------------------------------------------------


def stub_retriever(state: AgentState) -> dict:
    return {"chunks": [], "trace": [{"node": "retriever", "stub": True}]}


def oracle_loader_never_called(ref: str) -> QuantumCircuit:
    raise AssertionError(
        f"the product path (no oracle_ref) loaded oracle {ref!r} — semantic_check or "
        "resource_check was reached without a reference, which route_after_assertion_check "
        "must never allow"
    )


def bell_oracle_loader(ref: str) -> QuantumCircuit:
    qc = QuantumCircuit(2)
    qc.h(0)
    qc.cx(0, 1)
    return qc


class Run:
    def __init__(self, graph, planner, generator, critic, max_iter: int) -> None:
        self.graph = graph
        self.planner = planner
        self.generator = generator
        self.critic = critic
        self.max_iter = max_iter

    def invoke(self, state: AgentState) -> dict:
        return self.graph.invoke(
            state, config={"recursion_limit": recursion_limit_for(self.max_iter)}
        )


def build(
    pool: WorkerPool,
    tmp_path: Path,
    *,
    generator_responses: list[str],
    critic_responses: list[str] | None = None,
    planner_responses: list[str] | None = None,
    oracle_loader: Callable[[str], QuantumCircuit] = oracle_loader_never_called,
    max_iter: int = 5,
    resource_opt_level: int = 2,
) -> Run:
    planner = RecordingLLMClient(planner_responses or [planner_json()], tmp_path / "planner")
    generator = RecordingLLMClient(generator_responses, tmp_path / "generator")
    critic = RecordingLLMClient(critic_responses or [], tmp_path / "critic")
    graph = build_graph(
        planner_node=make_planner_node(planner, max_qubits=20),
        retriever_node=stub_retriever,
        generator_node=make_generator_node(generator),
        static_check_node=make_static_check_node(pool),
        assertion_check_node=make_assertion_check_node(),
        semantic_check_node=make_semantic_check_node(oracle_loader),
        resource_check_node=make_resource_check_node(oracle_loader, opt_level=resource_opt_level),
        critic_node=make_critic_node(critic, max_iter=max_iter),
    )
    return Run(graph, planner, generator, critic, max_iter)


def product_state(
    assertions_text: str | None = None,
    *,
    spec: str = "Build a 2-qubit Bell state",
    coupling_map_name: str | None = None,
) -> AgentState:
    """No `oracle_ref` key at all: the general product path."""
    state: AgentState = {
        "task_id": "product",
        "spec": spec,
        "coupling_map_name": coupling_map_name,
        "iteration": 0,
    }
    if assertions_text is not None:
        state["assertions_text"] = assertions_text
    return state


# -- Cross-cutting invariant --------------------------------------------------


def assert_status_and_report_agree(result: dict) -> tuple[GuaranteeReport, str]:
    """The F8 invariant, checked on every run that reaches `finalize`: the
    machine-readable `status` and the human-readable verdict must say the
    same thing about whether functional correctness was verified. Returns
    the report and its rendered text for further assertions."""
    report = result["guarantee_report"]
    assert isinstance(report, GuaranteeReport)
    text = render_guarantee_report(report)
    verified = report.functional_correctness_verified

    if result["status"] in ("success", "completed_unverified"):
        assert verified == (result["status"] == "success"), (
            f"status={result['status']!r} but functional_correctness_verified={verified}:\n{text}"
        )
    if verified:
        assert report.executed and report.transpiled, f"VERIFIED about code that never ran:\n{text}"
        # Verified-but-not-success is honest in exactly one case: functional
        # correctness passed and the loop was cut off on RESOURCES alone (the
        # resource line then says EXCEEDS). Anything else is an over-claim.
        if result["status"] != "success":
            assert report.resource is not None and not report.resource.passed, (
                f"report claims VERIFIED but status={result['status']!r}:\n{text}"
            )
    verdict = next(line for line in text.splitlines() if line.startswith("FUNCTIONAL CORRECTNESS"))
    assert verdict.startswith("FUNCTIONAL CORRECTNESS: VERIFIED") == verified, text
    return report, text
