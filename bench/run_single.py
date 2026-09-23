"""Manual, single-task inspection entrypoint for the graph (T024-T030,
T039).

    make run TASK=bench/tasks/t1_primitives/ghz_3q.json

Development tool, not part of the experimental harness: it always uses the
local Ollama generator (D10) and the real retriever against `settings.
qdrant_url` (`make index` must have populated the `qdocs` collection first —
this tool never creates it on demand, see index.py's CollectionNotFound), and
it prints a human-readable report instead of writing a `RunRecord` to
`results/`.

`run_task()` is the one piece meant to be reused: bench/runner.py (Phase 5,
not yet built) will need the same "load a task, load its oracle, build the
graph, invoke it" sequence for every row of the experimental matrix. Import
it from there instead of re-deriving it — that's the whole reason the
loading logic isn't just inlined under `if __name__ == "__main__"`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from pydantic import BaseModel
from qdrant_client import QdrantClient
from qiskit import qpy
from qiskit.quantum_info import SparsePauliOp

from bench.schema import TaskSpec
from qcagent.config import settings
from qcagent.graph import Oracle, StatePreparationOracle, recursion_limit_for
from qcagent.live import LiveServices, build_live_graph, initial_state
from qcagent.llm.ollama_client import OllamaClient
from qcagent.nodes.generator import render_structural_diff
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.state import AgentState
from qcagent.validators.sandbox import WorkerPool


def _load_oracle(task: TaskSpec) -> Oracle:
    # "unitary" and "statevector" (D3c, research.md) share the exact same
    # QPY reference-circuit file format — the only difference is which
    # semantic check the loaded object is dispatched to (see
    # StatePreparationOracle's docstring in graph.py), so both branches load
    # identically and only differ in whether the circuit gets wrapped.
    if task.oracle_kind in ("unitary", "statevector"):
        with open(task.oracle_path, "rb") as f:
            (circuit,) = qpy.load(f)
        if task.oracle_kind == "statevector":
            return StatePreparationOracle(reference_circuit=circuit)
        return circuit
    if task.oracle_kind == "energy":
        # Not a circuit — a Hamiltonian + its exact ground energy (D3e,
        # research.md). QPY has no format for a bare operator, so this is
        # JSON, built by bench/oracles/build_t2_vqe_h2.py.
        with open(task.oracle_path) as f:
            payload = json.load(f)
        hamiltonian = SparsePauliOp(payload["pauli_labels"], coeffs=payload["coeffs"])
        return hamiltonian, float(payload["exact_ground_energy"])
    raise NotImplementedError(
        f"oracle_kind={task.oracle_kind!r} has no loader yet — bench/oracles/ "
        "construction (T049) hasn't defined a format for it. This dev tool only "
        "supports 'unitary', 'statevector', and 'energy'."
    )


def run_task(task_path: Path, *, seed: int, max_iter: int | None = None) -> AgentState:
    """Runs one TaskSpec through the graph to a terminal status.

    `seed` is REQUIRED and is the whole point of T104. This tool used to pass
    none at all, so every by-hand run silently used the node defaults (42)
    while the suite ran 1/2/3 — and there was no flag to change it. An
    observation made here was therefore NOT comparable to the suite's numbers
    for the same task, which nothing said out loud (F20).

    It matters concretely: in the last clean suite run `ghz_3q` succeeds on
    seed 2 and fails on 1 and 3. A demo without a stated seed is a coin flip.
    """
    task = TaskSpec.model_validate_json(task_path.read_text())
    oracle = _load_oracle(task)
    # Every generation parameter stated explicitly, none inherited: this tool
    # and the suite agreed on temperature only because both happened to take
    # the client's default, which is the accident T104 exists to remove.
    llm = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_model,
        settings.ollama_num_ctx,
        settings.ollama_temperature,
    )
    resolved_max_iter = max_iter or settings.max_iter

    qdrant_client = QdrantClient(url=settings.qdrant_url)
    embedder = FastEmbedEmbedder()

    with WorkerPool(
        size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after
    ) as pool:
        graph = build_live_graph(
            LiveServices(llm=llm, qdrant=qdrant_client, embedder=embedder, pool=pool),
            seed=seed,
            max_iter=resolved_max_iter,
            oracle=oracle,
            distribution_tolerance=task.tolerance,
        )
        # LangGraph's CompiledStateGraph.invoke() is typed to return a plain
        # dict (it has no way to know the state is our AgentState TypedDict
        # at the type level) — the cast documents what's actually true at
        # runtime: this graph was built with StateGraph(AgentState), so
        # every key it returns is one of AgentState's.
        return cast(
            AgentState,
            graph.invoke(
                initial_state(
                    task_id=task.task_id,
                    spec=task.prompt,
                    oracle_ref=task.oracle_path,
                    coupling_map_name=task.coupling_map,
                    max_depth_ratio=task.max_depth_ratio,
                ),
                config={"recursion_limit": recursion_limit_for(resolved_max_iter)},
            ),
        )


def _print_report(state: AgentState) -> None:
    print(f"status: {state.get('status')}")
    print(f"iteration: {state.get('iteration')}")

    print("\n-- final code " + "-" * 60)
    print(state.get("code") or "<no code generated>")

    for layer in ("static", "semantic", "resource"):
        # `layer` is a plain str, not a Literal, so AgentState.get(layer)
        # widens to the union of every value type AgentState declares — cast
        # back to what these three keys are actually declared as
        # (StaticResult | SemanticResult | ResourceResult | None).
        result = cast("BaseModel | None", state.get(layer))
        print(f"\n-- {layer}_check " + "-" * (60 - len(layer)))
        if result is None:
            print("<not run>")
        else:
            # circuit_qpy is raw binary — never JSON-safe, and not
            # interesting for a by-hand report.
            dump = result.model_dump(exclude={"circuit_qpy"})
            print(json.dumps(dump, indent=2, default=str))

    error_history = state.get("error_history", [])
    print(f"\n-- error_history ({len(error_history)}) " + "-" * 40)
    for err in error_history:
        print(f"  [iter {err.iteration}] {err.stage}/{err.error_type}: {err.message}")
        # Reuses the exact same renderer the generator's own prompt uses
        # (nodes/generator.py) — what you see here must match what the
        # model received, not a second formatter drifting out of sync.
        if err.payload:
            diff = render_structural_diff(err.payload)
            if diff:
                print(diff)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path, help="Path to a TaskSpec JSON file")
    parser.add_argument(
        "--seed",
        type=int,
        default=1,
        help=(
            "Generator seed. Defaults to 1, which is a SUITE seed, so a run here is "
            "comparable to the suite's record for the same task. Outcomes differ by "
            "seed (ghz_3q succeeds on 2, fails on 1 and 3), so state it when reporting."
        ),
    )
    args = parser.parse_args()

    if not args.task.exists():
        print(f"error: task file not found: {args.task}", file=sys.stderr)
        raise SystemExit(1)

    print(f"seed={args.seed}  (outcomes are seed-dependent — see --seed)", file=sys.stderr)
    state = run_task(args.task, seed=args.seed)
    _print_report(state)


if __name__ == "__main__":
    main()
