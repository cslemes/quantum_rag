"""The ONE assembly of the live graph (T104).

Every caller that runs the real system against real services builds the graph
here: the regression suite, the by-hand inspection tool, and the interface.
Before this module they each assembled it themselves, and they had already
drifted:

* `run_single.py` passed NO seed, so every by-hand run used the node defaults
  (42) while the suite ran seeds 1/2/3 — and `run_single` had no flag to
  change it. Observations made there are therefore not comparable to suite
  numbers for the same task (see report-notes.md F20).
* `run_single.py` used `WorkerPool(size=2)`, the suite `size=6` from settings.
* `max_qubits=20` was hardcoded twice.

None of those differences were decided; they accumulated. A third copy for the
interface would have made a demo that diverges from the measured system, which
is the one thing a demo must not do.

`seed` is REQUIRED and has no default here, deliberately. A default is what
produced the drift: two callers silently disagreeing while both looked
correct. The suite passes its configured seed, the inspection tool passes the
one the user asked for, and the interface passes one it states.
"""

from collections.abc import Callable
from dataclasses import dataclass

from qdrant_client import QdrantClient

from qcagent.graph import (
    Oracle,
    build_graph,
    make_assertion_check_node,
    make_resource_check_node,
    make_semantic_check_node,
    make_static_check_node,
)
from qcagent.llm.base import BaseLLMClient
from qcagent.nodes.critic import make_critic_node
from qcagent.nodes.generator import make_generator_node
from qcagent.nodes.planner import make_planner_node
from qcagent.nodes.retriever import make_retriever_node
from qcagent.retrieval.embedding import Embedder
from qcagent.validators.sandbox import WorkerPool

# The simulation ceiling (D3b/data-model.md). One definition, because it was
# previously written out at each call site and would drift the same way.
MAX_QUBITS = 20


class NoOracleError(RuntimeError):
    """Raised if a reference oracle is requested on a run that has none.

    The interface path (US6) has no reference: a user describes a circuit,
    and there is nothing to compare it against. Routing already skips the
    reference checks when `oracle_ref` is absent, so this should be
    unreachable — it exists so that a routing change which breaks that
    assumption fails loudly here instead of silently comparing against
    something invented.
    """


@dataclass(frozen=True)
class LiveServices:
    """The live dependencies a real run needs. Grouped so the assembly
    signature states them once and no caller can forget one."""

    llm: BaseLLMClient
    qdrant: QdrantClient
    embedder: Embedder
    pool: WorkerPool


def build_live_graph(
    services: LiveServices,
    *,
    seed: int,
    max_iter: int,
    oracle: Oracle | None = None,
    distribution_tolerance: float | None = None,
    max_qubits: int = MAX_QUBITS,
):
    """Assembles the real graph. `oracle=None` is the interface path, where
    there is no reference to verify against and the guarantee report says so.

    Returns the compiled graph; the caller owns `services.pool` and decides
    its lifetime (the suite shares one across hundreds of runs, D1b).
    """

    def oracle_loader(_ref: str) -> Oracle:
        if oracle is None:
            raise NoOracleError(
                "a reference check was reached on a run with no oracle — routing should "
                "have skipped it (routing.py::route_after_assertion_check)"
            )
        return oracle

    # The default for `distribution_tolerance` lives in graph.py and stays
    # there: copying its value here would create exactly the second definition
    # this module exists to remove.
    semantic_node = (
        make_semantic_check_node(oracle_loader)
        if distribution_tolerance is None
        else make_semantic_check_node(oracle_loader, distribution_tolerance=distribution_tolerance)
    )
    return build_graph(
        planner_node=make_planner_node(services.llm, max_qubits=max_qubits, seed=seed),
        retriever_node=make_retriever_node(services.qdrant, services.embedder),
        generator_node=make_generator_node(services.llm, seed=seed),
        static_check_node=make_static_check_node(services.pool),
        assertion_check_node=make_assertion_check_node(),
        semantic_check_node=semantic_node,
        resource_check_node=make_resource_check_node(oracle_loader),
        critic_node=make_critic_node(services.llm, max_iter=max_iter, seed=seed),
    )


def initial_state(
    *,
    task_id: str,
    spec: str,
    oracle_ref: str | None = None,
    coupling_map_name: str | None = None,
    max_depth_ratio: float | None = None,
    assertions_text: str | None = None,
) -> dict:
    """The graph's entry state, built in one place for the same reason the
    graph is. `iteration=0` is not optional — the generator increments it and
    the critic compares it to `max_iter`."""
    state: dict = {
        "task_id": task_id,
        "spec": spec,
        "oracle_ref": oracle_ref,
        "coupling_map_name": coupling_map_name,
        "max_depth_ratio": max_depth_ratio,
        "iteration": 0,
    }
    if assertions_text is not None:
        state["assertions_text"] = assertions_text
    return state


Runner = Callable[..., object]
