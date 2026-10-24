"""The negative control: does the PIPELINE reject a wrong circuit?

A filter that accepted 40 of 40 on first contact has not been shown to filter.
The strict check has unit tests; that is not the same as the pipeline (statement
-> teacher call -> code extraction -> sandbox -> family check -> label) rejecting
a wrong answer and recording why. So, before any real call, the real
`run_pilot` is driven over a mock transport that answers with:

* per family, one deliberately WRONG circuit: permutations: a different
  permutation; graph states: one CZ edge missing; Pauli energy: the basis state
  of highest energy; biased bits: the bit-reversed biases;
* one program that does not even parse (a static failure, for its reason code);
* per family, one CORRECT circuit, so that "rejects everything" cannot pass.

The control FIRES when every wrong answer is unlabelled with a reason code and
every correct one is labelled. No network, no credential, no spend: the
transport is a local function and the client key is a placeholder.
"""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from qiskit.quantum_info import SparsePauliOp

from qcagent.distill.families import Family, Variation
from qcagent.distill.families.permutations import cycles
from qcagent.distill.gate import StatementRegistry
from qcagent.distill.pilot import LABEL, SpendAuthorization, run_pilot
from qcagent.distill.spend import SpendGuard, estimate_from_tokens
from qcagent.llm.openai_compatible_client import OpenAICompatibleClient
from qcagent.llm.profiles import Profile
from qcagent.validators.sandbox import WorkerPool


def _fence(code: str) -> str:
    return "```python\n" + code.strip() + "\n```"


def _swap_code(pi: list[int]) -> str:
    lines = ["from qiskit import QuantumCircuit", f"qc = QuantumCircuit({len(pi)})"]
    for cycle in cycles(pi):
        lines += [f"qc.swap({cycle[j]}, {cycle[j + 1]})" for j in range(len(cycle) - 2, -1, -1)]
    return _fence("\n".join(lines))


def _graph_code(n: int, edges: list[list[int]]) -> str:
    lines = [
        "from qiskit import QuantumCircuit",
        f"qc = QuantumCircuit({n})",
        f"qc.h(range({n}))",
    ]
    lines += [f"qc.cz({i}, {j})" for i, j in edges]
    return _fence("\n".join(lines))


def _ry_code(p: list[float]) -> str:
    lines = [
        "import numpy as np",
        "from qiskit import QuantumCircuit",
        f"p = {list(p)!r}",
        f"qc = QuantumCircuit({len(p)})",
        "for i, p_i in enumerate(p):",
        "    qc.ry(2 * np.arcsin(np.sqrt(p_i)), i)",
        "qc.measure_all()",
    ]
    return _fence("\n".join(lines))


def _energy_code(vector: np.ndarray, n: int) -> str:
    amps = ", ".join(f"complex({a.real!r}, {a.imag!r})" for a in vector)
    lines = [
        "from qiskit import QuantumCircuit",
        "from qiskit.circuit.library import StatePreparation",
        f"qc = QuantumCircuit({n})",
        f"qc.append(StatePreparation([{amps}]), range({n}))",
    ]
    return _fence("\n".join(lines))


def _energy_states(v: Variation) -> tuple[np.ndarray, np.ndarray]:
    labels, coeffs = v.params["labels"], v.params["coeffs"]
    matrix = SparsePauliOp(labels, coeffs=coeffs).to_matrix()
    _, vectors = np.linalg.eigh(matrix)
    highest_basis = int(np.argmax(np.real(np.diag(matrix))))
    wrong = np.zeros(1 << v.params["n"], dtype=complex)
    wrong[highest_basis] = 1.0
    return vectors[:, 0], wrong


def correct_code(family: Family, v: Variation) -> str:
    if family.name == "qubit_permutation":
        return _swap_code(v.params["pi"])
    if family.name == "graph_state":
        return _graph_code(v.params["n"], v.params["edges"])
    if family.name == "pauli_hamiltonian_energy":
        return _energy_code(_energy_states(v)[0], v.params["n"])
    return _ry_code(v.params["p"])


def wrong_code(family: Family, v: Variation) -> str:
    """A circuit that is plausible code for the statement and wrong for its oracle."""
    if family.name == "qubit_permutation":
        pi = list(v.params["pi"])
        other = pi[:]
        other[0], other[1] = other[1], other[0]  # a different permutation
        assert other != pi
        return _swap_code(other)
    if family.name == "graph_state":
        return _graph_code(v.params["n"], v.params["edges"][:-1])  # one CZ edge missing
    if family.name == "pauli_hamiltonian_energy":
        return _energy_code(_energy_states(v)[1], v.params["n"])
    p = list(reversed(v.params["p"]))  # bit-reversed biases
    return _ry_code(p)


SYNTAX_ERROR = _fence("from qiskit import QuantumCircuit\nqc = QuantumCircuit(2\n")


def run_negative_control(
    *,
    families: tuple[Family, ...],
    profile: Profile,
    snapshot: dict[str, Any],
    pool: WorkerPool,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Drive the real pipeline over a local transport. Returns the report; the
    control `fired` only if every wrong answer was rejected with a reason code
    and every correct one was labelled."""
    work = work_dir or Path(tempfile.mkdtemp(prefix="distill-negative-control-"))
    work.mkdir(parents=True, exist_ok=True)
    registry = StatementRegistry(work / "registry.jsonl")
    plan: dict[str, tuple[str, str]] = {}  # statement text -> (kind, code)
    chosen: dict[str, tuple[str, str]] = {}  # statement id -> (family, kind)
    for family in families:
        registry.admit_family(family)
        v_wrong, v_right = family.variations()[0], family.variations()[1]
        for v, kind, code in (
            (v_wrong, "wrong", wrong_code(family, v_wrong)),
            (v_right, "correct", correct_code(family, v_right)),
        ):
            text = family.statement(v)
            plan[text] = (kind, code)
            chosen[_id(registry, text)] = (family.name, kind)
    first = families[0]
    v_bad = first.variations()[2]
    plan[first.statement(v_bad)] = ("unparseable", SYNTAX_ERROR)
    chosen[_id(registry, first.statement(v_bad))] = (first.name, "unparseable")

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        _, code = plan[body["messages"][1]["content"]]
        return httpx.Response(
            200,
            json={
                "id": "control",
                "model": profile.model,
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": code}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
            },
        )

    assert profile.provider_options is not None
    client = OpenAICompatibleClient(
        "control-placeholder-not-a-credential",
        profile.model,
        "http://control.invalid/api/v1",
        temperature=profile.determinism.temperature,
        top_p=profile.determinism.top_p,
        provider_options=profile.provider_options.as_body(),
        reasoning_effort=profile.reasoning_effort,
        max_tokens_headroom=profile.max_tokens_headroom,
    )
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    client.cache_dir = work / "cache"  # never the real cache

    now = datetime.now(UTC)
    summary = run_pilot(
        registry=registry,
        families=families,
        client=client,
        profile=profile,
        out_dir=work / "out",
        guard=SpendGuard(estimate_usd=0.01),
        estimate=estimate_from_tokens(len(chosen), 1, 1, now=now),
        dataset_version="negative-control",
        pool=pool,
        snapshot=snapshot,
        authorization=SpendAuthorization(
            ceiling_usd=1.0, granted_by="negative control: local transport, no network, no spend"
        ),
        only_ids=set(chosen),
    )
    rows = []
    for line in (work / "out" / "records.jsonl").read_text().splitlines():
        r = json.loads(line)
        family_name, kind = chosen[r["statement_id"]]
        labelled = r["label"] == LABEL
        ok = labelled if kind == "correct" else (not labelled and r["reject_reason"] is not None)
        rows.append(
            {
                "family": family_name,
                "injected": kind,
                "labelled": labelled,
                "reject_reason": r["reject_reason"],
                "acceptance": r["acceptance"],
                "behaved_as_required": ok,
            }
        )
    fired = len(rows) == len(chosen) and all(r["behaved_as_required"] for r in rows)
    return {
        "fired": fired,
        "rows": rows,
        "work_dir": str(work),
        "halted": summary["halted"],
        "wrong_rejected": sum(1 for r in rows if r["injected"] != "correct" and not r["labelled"]),
        "correct_accepted": sum(1 for r in rows if r["injected"] == "correct" and r["labelled"]),
    }


def _id(registry: StatementRegistry, text: str) -> str:
    from qcagent.distill.gate import statement_id

    sid = statement_id(text)
    assert any(e["id"] == sid for e in registry.entries())
    return sid
