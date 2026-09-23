"""T042 — integration test for User Story 2's retrieval wiring (T039).

Covers the three US2 acceptance scenarios from spec.md, plus the retry-reuse
constraint the task explicitly calls out: retry_retrieval is the only action
that issues a new Qdrant query — retry_generation and optimize must reuse
`state["chunks"]` unchanged, or conditions C3 and C5 become indistinguishable
on the one axis H1's ablation depends on.

Real `:memory:` Qdrant + a real `FastEmbedEmbedder` (same pattern as
test_hybrid.py's RZGate/RXGate case) — no live server required, but the
actual prefetch+fusion query path runs for real. The LLM stays scripted
(`ScriptedLLMClient`, same pattern as test_us1_flow.py); this file tests
wiring, not generation quality.
"""

from pathlib import Path

import pytest
from qdrant_client import QdrantClient
from qiskit import QuantumCircuit

from qcagent.graph import (
    build_graph,
    make_assertion_check_node,
    make_resource_check_node,
    make_semantic_check_node,
    make_static_check_node,
)
from qcagent.llm.base import BaseLLMClient, LLMResponse
from qcagent.nodes.critic import make_critic_node
from qcagent.nodes.generator import make_generator_node
from qcagent.nodes.planner import make_planner_node
from qcagent.nodes.retriever import make_retriever_node
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.retrieval.index import ensure_collection, upsert_chunks
from qcagent.retrieval.ingest import LIBRARY_VERSION
from qcagent.state import Chunk
from qcagent.validators.sandbox import WorkerPool
from qcagent.validators.static import DEPRECATED_SYMBOLS

BELL_ORACLE = QuantumCircuit(2)
BELL_ORACLE.h(0)
BELL_ORACLE.cx(0, 1)

VALID_BELL_CODE = (
    "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\n"
)

# "execute(...)" is one of static.py's own DEPRECATED_SYMBOLS — a real
# removed-in-1.0 construct, not a fabricated one — so the DeprecatedAPI path
# this exercises is the genuine one the critic table routes to retry_retrieval.
OBSOLETE_CODE = (
    "from qiskit import QuantumCircuit, execute\n"
    "qc = QuantumCircuit(2)\nqc.h(0)\nqc.cx(0, 1)\nexecute(qc)\n"
)

# Fails semantic_check (X instead of the H+CX Bell prep) without touching any
# deprecated symbol -> WrongGateDecomposition -> retry_generation, the action
# constraint #1 says must NOT requery.
WRONG_GATE_CODE = "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.x(0)\n"

# CX is self-inverse: 5 repeats is functionally a Bell pair but structurally
# 5x heavier -> ResourceExcess -> optimize, the other action constraint #1
# says must NOT requery. Same construction as test_us1_flow.py's HEAVY_BELL_CODE.
HEAVY_BELL_CODE = (
    "from qiskit import QuantumCircuit\nqc = QuantumCircuit(2)\nqc.h(0)\n" + "qc.cx(0, 1)\n" * 5
)

REQUIREMENTS_JSON = """{"satisfiable": true, "rejection_reason": null, "requirements": [
    {"id": "r1", "kind": "n_qubits", "description": "2 qubits", "value": 2},
    {"id": "r2", "kind": "property", "description": "produce a Bell state", "value": null}
]}"""

CRITIC_HINT_JSON = '{"rationale": "fix and retry", "hint": "try again more carefully"}'


class ScriptedLLMClient(BaseLLMClient):
    """One scripted response per call, in order, and every prompt it was
    called with recorded — needed to inspect what the generator actually saw
    (scenario 3). Distinct cache_dir per instance so repeated calls always
    advance instead of hitting a stale cache entry."""

    model_id = "scripted-fake"

    def __init__(self, responses: list[str], cache_dir: Path) -> None:
        self.responses = responses
        self.calls = 0
        self.cache_dir = cache_dir
        self.prompts: list[str] = []

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        self.prompts.append(prompt)
        text = self.responses[self.calls]
        self.calls += 1
        return LLMResponse(
            text=text,
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_s=0.001,
            model_id=self.model_id,
        )


class _CountingClientProxy:
    """Wraps a real QdrantClient, counting `query_points` calls.
    `hybrid.search` only ever calls `collection_exists` and `query_points` on
    the client it's given, so forwarding just those two is enough to stand in
    for the real client while observing how many times a retrieval actually
    fired — the authoritative check for constraint #1, beneath the node's own
    `trace` flags.
    """

    def __init__(self, client: QdrantClient) -> None:
        self._client = client
        self.query_points_calls = 0

    def collection_exists(self, *args, **kwargs):
        return self._client.collection_exists(*args, **kwargs)

    def query_points(self, *args, **kwargs):
        self.query_points_calls += 1
        return self._client.query_points(*args, **kwargs)


def _oracle_loader(_ref: str) -> QuantumCircuit:
    return BELL_ORACLE


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=100) as p:
        yield p


@pytest.fixture(scope="module")
def embedder() -> FastEmbedEmbedder:
    return FastEmbedEmbedder()


def _seeded_client(embedder: FastEmbedEmbedder) -> _CountingClientProxy:
    """A fresh `:memory:` collection per test, seeded with a small corpus
    that deliberately contains BOTH a current construct and a deprecated
    sibling with its replacement — U3Gate was a real hallucination source
    (research.md D17) before the corpus carried it marked obsolete, which is
    exactly the case this file needs to prove retrieval now prevents.
    """
    raw_client = QdrantClient(":memory:")
    chunks = [
        Chunk(
            doc_id="QuantumCircuit.u",
            text=(
                "[method] QuantumCircuit.u — apply a generic single-qubit "
                "rotation gate with parameters theta, phi, lambda."
            ),
            source="qiskit_api",
            library_version=LIBRARY_VERSION,
            score=0.0,
        ),
        Chunk(
            doc_id="U3Gate",
            text=(
                "[class] U3Gate — generic single-qubit rotation gate. This "
                "gate is deprecated. Use circuit.u(theta, phi, lambda) instead."
            ),
            source="qiskit_api",
            library_version=LIBRARY_VERSION,
            deprecated=True,
            replacement="QuantumCircuit.u()",
            score=0.0,
        ),
        Chunk(
            doc_id="QuantumCircuit.h",
            text="[method] QuantumCircuit.h — apply a Hadamard gate.",
            source="qiskit_api",
            library_version=LIBRARY_VERSION,
            score=0.0,
        ),
        Chunk(
            doc_id="QuantumCircuit.cx",
            text="[method] QuantumCircuit.cx — apply a controlled-X (CNOT) gate.",
            source="qiskit_api",
            library_version=LIBRARY_VERSION,
            score=0.0,
        ),
    ]
    ensure_collection(raw_client, embedder.dense_dim)
    dense = embedder.embed_documents([c.text for c in chunks])
    sparse = embedder.embed_sparse_documents([c.text for c in chunks])
    upsert_chunks(raw_client, chunks, dense, sparse)
    return _CountingClientProxy(raw_client)


def _build(
    pool: WorkerPool,
    embedder: FastEmbedEmbedder,
    tmp_path: Path,
    *,
    generator_responses: list[str],
    critic_responses: list[str],
    max_iter: int = 5,
    resource_opt_level: int = 2,
):
    proxy = _seeded_client(embedder)
    planner_llm = ScriptedLLMClient([REQUIREMENTS_JSON], tmp_path / "planner_cache")
    generator_llm = ScriptedLLMClient(generator_responses, tmp_path / "generator_cache")
    critic_llm = ScriptedLLMClient(critic_responses, tmp_path / "critic_cache")

    graph = build_graph(
        planner_node=make_planner_node(planner_llm, max_qubits=20),
        # proxy only implements the two methods hybrid.search() actually
        # calls on a QdrantClient (see _CountingClientProxy's docstring) —
        # not a real QdrantClient, hence the ignore.
        retriever_node=make_retriever_node(proxy, embedder, limit=8),  # type: ignore[arg-type]
        generator_node=make_generator_node(generator_llm),
        static_check_node=make_static_check_node(pool),
        assertion_check_node=make_assertion_check_node(),
        semantic_check_node=make_semantic_check_node(_oracle_loader),
        resource_check_node=make_resource_check_node(_oracle_loader, opt_level=resource_opt_level),
        critic_node=make_critic_node(critic_llm, max_iter=max_iter),
    )
    return graph, proxy, generator_llm, critic_llm


def _initial_state(
    spec: str = (
        "Build a 2-qubit circuit using the current single-qubit rotation API "
        "(not u3, which is deprecated)"
    ),
):
    return {
        "task_id": "t-us2",
        "spec": spec,
        "oracle_ref": "bell",
        "coupling_map_name": None,
        "iteration": 0,
    }


# -- Scenario 1: renamed construct -> artifact uses the current one ---------


def test_scenario1_generated_artifact_uses_current_construct(
    pool: WorkerPool, embedder: FastEmbedEmbedder, tmp_path: Path
) -> None:
    graph, proxy, generator_llm, critic_llm = _build(
        pool,
        embedder,
        tmp_path,
        generator_responses=[f"```python\n{VALID_BELL_CODE}```"],
        critic_responses=[],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 1
    # Retrieval actually ran and surfaced real corpus content, including the
    # deprecated sibling — proves this isn't succeeding by accident of an
    # empty context.
    assert result["chunks"]
    assert any(c.doc_id == "U3Gate" and c.deprecated for c in result["chunks"])
    assert not any(symbol in result["code"] for symbol in DEPRECATED_SYMBOLS)


# -- Scenario 2: obsolete construct -> re-query before regenerating ---------


def test_scenario2_deprecated_api_triggers_a_real_requery_before_regenerating(
    pool: WorkerPool, embedder: FastEmbedEmbedder, tmp_path: Path
) -> None:
    graph, proxy, generator_llm, critic_llm = _build(
        pool,
        embedder,
        tmp_path,
        generator_responses=[
            f"```python\n{OBSOLETE_CODE}```",
            f"```python\n{VALID_BELL_CODE}```",
        ],
        critic_responses=[CRITIC_HINT_JSON],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert result["error_history"][0].error_type == "DeprecatedAPI"
    # Not "just repeats generation": the retriever issued a SECOND real
    # Qdrant query, not a second generation attempt over stale context.
    assert proxy.query_points_calls == 2
    retriever_trace = [t for t in result["trace"] if t.get("node") == "retriever"]
    assert [t["queried"] for t in retriever_trace] == [True, True]


# -- Scenario 3: obsolete material reaches the generator explicitly labeled -


def test_scenario3_deprecated_chunks_reach_generator_labeled_not_filtered(
    pool: WorkerPool, embedder: FastEmbedEmbedder, tmp_path: Path
) -> None:
    graph, proxy, generator_llm, critic_llm = _build(
        pool,
        embedder,
        tmp_path,
        generator_responses=[f"```python\n{VALID_BELL_CODE}```"],
        critic_responses=[],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert generator_llm.prompts, "generator must have been called at least once"
    prompt = generator_llm.prompts[0]
    # FR-014/D7: labeled unusable with its replacement, not omitted.
    assert "[OBSOLETO — NÃO USAR] U3Gate" in prompt
    assert "Substituir por: QuantumCircuit.u()" in prompt


# -- Constraint: retry_generation must reuse chunks, never requery ----------


def test_retry_generation_reuses_chunks_without_requerying(
    pool: WorkerPool, embedder: FastEmbedEmbedder, tmp_path: Path
) -> None:
    graph, proxy, generator_llm, critic_llm = _build(
        pool,
        embedder,
        tmp_path,
        generator_responses=[
            f"```python\n{WRONG_GATE_CODE}```",
            f"```python\n{VALID_BELL_CODE}```",
        ],
        critic_responses=[CRITIC_HINT_JSON],
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert result["error_history"][0].error_type == "WrongGateDecomposition"
    # retry_generation reuses state["chunks"] as-is — only ONE real query for
    # the whole run, at the initial retrieval before iteration 1.
    assert proxy.query_points_calls == 1
    retriever_trace = [t for t in result["trace"] if t.get("node") == "retriever"]
    assert [t["queried"] for t in retriever_trace] == [True, False]


# -- Constraint: optimize must also reuse chunks, never requery -------------


def test_optimize_reuses_chunks_without_requerying(
    pool: WorkerPool, embedder: FastEmbedEmbedder, tmp_path: Path
) -> None:
    graph, proxy, generator_llm, critic_llm = _build(
        pool,
        embedder,
        tmp_path,
        generator_responses=[
            f"```python\n{HEAVY_BELL_CODE}```",
            f"```python\n{VALID_BELL_CODE}```",
        ],
        critic_responses=[CRITIC_HINT_JSON],
        resource_opt_level=0,
    )

    result = graph.invoke(_initial_state())

    assert result["status"] == "success"
    assert result["iteration"] == 2
    assert result["error_history"][0].error_type == "ResourceExcess"
    assert proxy.query_points_calls == 1
    retriever_trace = [t for t in result["trace"] if t.get("node") == "retriever"]
    assert [t["queried"] for t in retriever_trace] == [True, False]
