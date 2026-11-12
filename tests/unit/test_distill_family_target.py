"""run_pilot's per-family stop: counts ACCEPTED records, goes round-robin, resume adds nothing.

Regression for the batch-v1 run, where the counting line was missing and every family ran to its
last admitted variation (70 paid calls instead of 35). Needs the sandbox (POSIX), so Docker/WSL.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from qcagent.distill.control import correct_code, wrong_code
from qcagent.distill.families import GraphStates, QubitPermutations
from qcagent.distill.gate import StatementRegistry
from qcagent.distill.listing import snapshot_facts
from qcagent.distill.pilot import LABEL, SpendAuthorization, run_pilot
from qcagent.distill.spend import SpendGuard, estimate_from_tokens
from qcagent.llm.openai_compatible_client import OpenAICompatibleClient
from qcagent.llm.profiles import get_profile
from qcagent.validators.sandbox import WorkerPool

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the sandbox needs POSIX select() on pipes"
)

FACTS = snapshot_facts(
    json.loads(
        (
            Path(__file__).parent / "data" / "openrouter_listing_deepseek_v4.1_flash_1017.json"
        ).read_text(encoding="utf-8")
    )
)
FAMILIES = (QubitPermutations(), GraphStates())
ADMITTED = 8
TARGET = 3


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=50) as p:
        yield p


def _setup(tmp_path: Path, wrong_first: str | None = None):
    """A registry of ADMITTED statements per family and a transport that answers each one
    correctly, except the first statement of `wrong_first`'s family, answered wrongly."""
    profile = get_profile("teacher-deepseek-v4.1-flash-1017")
    registry = StatementRegistry(tmp_path / "registry.jsonl")
    answers: dict[str, str] = {}
    for family in FAMILIES:
        registry.admit_family(family, ADMITTED)
        for i, v in enumerate(family.variations(ADMITTED)):
            broken = wrong_first == family.name and i == 0
            answers[family.statement(v)] = (wrong_code if broken else correct_code)(family, v)

    def handler(request: httpx.Request) -> httpx.Response:
        code = answers[json.loads(request.content)["messages"][1]["content"]]
        return httpx.Response(
            200,
            json={
                "id": "t",
                "model": profile.model,
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": code}}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
            },
        )

    assert profile.provider_options is not None
    client = OpenAICompatibleClient(
        "placeholder-not-a-credential",
        profile.model,
        "http://control.invalid/api/v1",
        temperature=profile.determinism.temperature,
        top_p=profile.determinism.top_p,
        provider_options=profile.provider_options.as_body(),
        reasoning_effort=profile.reasoning_effort,
        max_tokens_headroom=profile.max_tokens_headroom,
    )
    client._http = httpx.Client(transport=httpx.MockTransport(handler))
    client.cache_dir = tmp_path / "cache"
    return profile, registry, client


def _run(pool, tmp_path, profile, registry, client):
    return run_pilot(
        registry=registry,
        families=FAMILIES,
        client=client,
        profile=profile,
        out_dir=tmp_path / "out",
        guard=SpendGuard(estimate_usd=0.01),
        estimate=estimate_from_tokens(2 * ADMITTED, 1, 1, now=datetime.now(UTC)),
        dataset_version="target-test",
        pool=pool,
        snapshot=FACTS,
        authorization=SpendAuthorization(ceiling_usd=1.0, granted_by="test: local transport"),
        variation_count=ADMITTED,
        per_family_target=TARGET,
    )


def _records(tmp_path: Path) -> list[dict]:
    path = tmp_path / "out" / "records.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def test_each_family_stops_at_the_target_and_the_order_is_round_robin(pool, tmp_path) -> None:
    profile, registry, client = _setup(tmp_path)
    _run(pool, tmp_path, profile, registry, client)
    records = _records(tmp_path)
    assert len(records) == 2 * TARGET  # not 2 * ADMITTED
    assert [r["family"] for r in records[:2]] == ["qubit_permutation", "graph_state"]
    for family in FAMILIES:
        mine = [r for r in records if r["family"] == family.name]
        assert len(mine) == TARGET and all(r["label"] == LABEL for r in mine)


def test_it_counts_accepted_records_not_attempts(pool, tmp_path) -> None:
    profile, registry, client = _setup(tmp_path, wrong_first="graph_state")
    _run(pool, tmp_path, profile, registry, client)
    records = _records(tmp_path)
    graph = [r for r in records if r["family"] == "graph_state"]
    assert len(graph) == TARGET + 1  # the rejected one does not count toward the target
    assert sum(1 for r in graph if r["label"] == LABEL) == TARGET
    assert len([r for r in records if r["family"] == "qubit_permutation"]) == TARGET


def test_a_resumed_run_makes_no_further_calls(pool, tmp_path) -> None:
    profile, registry, client = _setup(tmp_path)
    _run(pool, tmp_path, profile, registry, client)
    before = len(_records(tmp_path))
    _run(pool, tmp_path, profile, registry, client)
    assert len(_records(tmp_path)) == before
