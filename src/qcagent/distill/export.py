"""The exporter: accepted teacher records -> `train.jsonl`, in exactly the shape the student sees.

    {"id", "family", "messages": [system, user], "completion"}

`messages` is what the harness sends the generator on ATTEMPT 1: `GENERATOR_SYSTEM_PROMPT` and
`_build_prompt(requirements, state, [])`, where `requirements` come from the STUDENT's own planner
and `chunks` from the real retriever, at the pinned server build and Qdrant index. Nothing is
hand-built: a prompt that skipped the planner or the retriever would be the wrong distribution.
`completion` is the teacher's accepted code as one fenced block.

Rules, none of them optional:
  * only statements that PASS the gate again at export time (`registry.export()`), and whose latest
    teacher record is labelled (oracle-verified, no circuit-level leak);
  * a statement whose planner call fails, is refused, or yields no requirements is NOT exported and
    is counted by reason, never patched up;
  * the planner and retriever are called once per statement, in a stable order, and the output file
    is byte-reproducible from the same inputs (sorted by family order then registry order);
  * the identity of everything that shaped the prompts is written next to the file
    (`train.meta.json`): teacher, student planner model and server build, index pin, gate version,
    counts, and the file's sha256. A dataset generated across a build or index change is a new
    dataset version.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qcagent.distill.gate import StatementRegistry
from qcagent.distill.pilot import LABEL
from qcagent.live import initial_state
from qcagent.nodes.generator import GENERATOR_SYSTEM_PROMPT, _build_prompt

#: AgentState -> the node's update, exactly as `make_planner_node` / `make_retriever_node` return it
Node = Callable[[dict], dict]


class ExportRefused(RuntimeError):
    """The inputs cannot produce a valid dataset (mixed identity, stale gate, short families)."""


def attempt1_messages(
    statement: str, statement_id: str, planner: Node, retriever: Node
) -> tuple[list[dict[str, str]] | None, str]:
    """The harness's attempt-1 messages for one statement, or (None, reason)."""
    state: dict[str, Any] = dict(initial_state(task_id=statement_id, spec=statement))
    state.update(planner(state))
    status = state.get("status")
    if status != "running":
        return None, f"planner:{status}"
    if not state.get("requirements"):
        return None, "planner:no_requirements"
    state.update(retriever(state))
    if not state.get("chunks"):
        # An empty context is a legitimate retrieval result in the harness, but for training it
        # would teach "no context", which is not what the student sees. Counted, not exported.
        return None, "retriever:no_chunks"
    user = _build_prompt(state["requirements"], state, [])
    return [
        {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ], ""


def fenced(code: str) -> str:
    return "```python\n" + code.strip() + "\n```"


def _latest_labelled(records_path: Path) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for line in records_path.read_text(encoding="utf-8").splitlines():
        if line:
            r = json.loads(line)
            latest[r["statement_id"]] = r
    return {sid: r for sid, r in latest.items() if r.get("label") == LABEL}


def export_dataset(
    *,
    registry: StatementRegistry,
    records_path: Path,
    meta_path: Path,
    out_path: Path,
    planner: Node,
    retriever: Node,
    environment: dict[str, Any],
    family_order: list[str],
    per_family: int | None = None,
) -> dict[str, Any]:
    """Writes `out_path` and `out_path.with_suffix('.meta.json')`. Returns the report.

    `environment` is the identity the prompts depend on and the caller must state (student planner
    model + digest, Ollama build, Qdrant index pin, quantisation); an empty one is refused.
    """
    if not environment:
        raise ExportRefused("no environment identity given: the prompts' provenance is required")
    dataset = json.loads(meta_path.read_text(encoding="utf-8"))
    passing = {e["id"]: e for e in registry.export()}  # re-runs the gate; GateStale / NotAdmitted
    labelled = _latest_labelled(records_path)
    unknown = sorted(set(labelled) - set(passing))
    if unknown:
        raise ExportRefused(f"{len(unknown)} labelled records are not gate-passing statements")

    order = {name: i for i, name in enumerate(family_order)}
    by_family: dict[str, list[dict[str, Any]]] = {}
    for record in labelled.values():
        by_family.setdefault(record["family"], []).append(record)
    # registry order within a family: the order statements were admitted,
    # not the order they finished
    registry_rank = {sid: i for i, sid in enumerate(passing)}

    rows: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    counts: dict[str, int] = {}
    for family in sorted(by_family, key=lambda f: order.get(f, len(order))):
        for record in sorted(by_family[family], key=lambda r: registry_rank[r["statement_id"]]):
            if per_family is not None and counts.get(family, 0) >= per_family:
                break
            messages, reason = attempt1_messages(
                record["statement"], record["statement_id"], planner, retriever
            )
            if messages is None:
                skipped[f"{family}:{reason}"] = skipped.get(f"{family}:{reason}", 0) + 1
                continue
            rows.append(
                {
                    "id": record["statement_id"],
                    "family": family,
                    "messages": messages,
                    "completion": fenced(record["code"]),
                }
            )
            counts[family] = counts.get(family, 0) + 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    out_path.write_text(text, encoding="utf-8", newline="\n")
    meta = {
        "dataset_version": dataset["dataset_version"],
        "teacher": dataset["identity"],
        "environment": environment,
        "gate_version": registry.gate_version,
        "rows": len(rows),
        "per_family": counts,
        "skipped": skipped,
        "per_family_target": per_family,
        "file_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    out_path.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    return meta
