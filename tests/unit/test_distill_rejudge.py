"""Re-judging stored answers: the selected verdicts are recomputed, the control must hold, the
source is never written, nothing is spent. Needs the sandbox (POSIX), so Docker/WSL.

The "wrong oracle of the past" is simulated by rewriting stored VERDICTS in the source records:
a right answer filed as rejected, a wrong answer filed as accepted. That is exactly the shape of
train-v1's qft inverse / no-SWAP cell (106 right answers rejected, 4 wrong ones accepted).
"""

from __future__ import annotations

import hashlib
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
from qcagent.distill.rejudge import RejudgeRefused, rejudge_dataset
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
ADMITTED = 4
REASON = "test: the oracle of two permutation statements was wrong"


@pytest.fixture(scope="module")
def pool():
    with WorkerPool(size=2, recycle_after=50) as p:
        yield p


def _source(tmp_path: Path, pool) -> Path:
    """A generated dataset: permutation variation 1 answered WRONGLY, everything else correctly."""
    profile = get_profile("teacher-deepseek-v4.1-flash-1017")
    source = tmp_path / "v1"
    source.mkdir()
    registry = StatementRegistry(source / "registry.jsonl")
    answers: dict[str, str] = {}
    for family in FAMILIES:
        registry.admit_family(family, ADMITTED)
        for v in family.variations(ADMITTED):
            wrong = family.name == "qubit_permutation" and v.index == 1
            answers[family.statement(v)] = (wrong_code if wrong else correct_code)(family, v)

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
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.001},
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
    run_pilot(
        registry=registry,
        families=FAMILIES,
        client=client,
        profile=profile,
        out_dir=source,
        guard=SpendGuard(estimate_usd=0.05),
        estimate=estimate_from_tokens(2 * ADMITTED, 1, 1, now=datetime.now(UTC)),
        dataset_version="v1",
        pool=pool,
        snapshot=FACTS,
        authorization=SpendAuthorization(ceiling_usd=1.0, granted_by="test: local transport"),
        variation_count=ADMITTED,
    )
    return source


def _records(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def _file_wrong_verdicts(source: Path) -> tuple[str, str]:
    """Rewrite two stored verdicts as a wrong oracle would have left them. Returns the ids:
    (the right answer now filed as rejected, the wrong answer now filed as accepted)."""
    records = _records(source / "records.jsonl")
    keys = {v.index: v.key for v in FAMILIES[0].variations(ADMITTED)}
    right = next(r for r in records if r["variation_key"] == keys[0])
    wrong = next(r for r in records if r["variation_key"] == keys[1])
    assert right["label"] == LABEL and wrong["label"] is None  # as generated: judged correctly
    right.update(label=None, reject_reason="rejected_by_oracle:strict_unitary")
    right.pop("leak_check", None)
    wrong.update(label=LABEL, reject_reason=None)
    (source / "records.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8", newline="\n"
    )
    return right["statement_id"], wrong["statement_id"]


def _rejudge(source: Path, out: Path, pool, **kw):
    return rejudge_dataset(
        source_dir=source,
        out_dir=out,
        families=kw.pop("families", (FAMILIES[0],)),
        variation_count=ADMITTED,
        pool=pool,
        dataset_version=kw.pop("dataset_version", "v2"),
        reason=kw.pop("reason", REASON),
        selects=kw.pop("selects", lambda family, v: v.index in (0, 1)),
    )


def test_selected_verdicts_are_recomputed_and_the_source_is_kept(pool, tmp_path) -> None:
    source = _source(tmp_path, pool)
    right_id, wrong_id = _file_wrong_verdicts(source)
    before = (source / "records.jsonl").read_bytes()
    summary = _rejudge(source, tmp_path / "v2", pool)

    assert (source / "records.jsonl").read_bytes() == before  # the source is never written
    new_bytes = (tmp_path / "v2" / "records.jsonl").read_bytes()
    assert new_bytes.startswith(before)  # the source records, byte for byte, then the appended ones
    appended = [json.loads(x) for x in new_bytes[len(before) :].decode().splitlines()]
    assert {r["statement_id"] for r in appended} == {right_id, wrong_id}
    by_id = {r["statement_id"]: r for r in appended}
    assert by_id[right_id]["label"] == LABEL and by_id[right_id]["reject_reason"] is None
    assert by_id[wrong_id]["label"] is None
    assert by_id[wrong_id]["reject_reason"].startswith("rejected_by_oracle")
    for r in appended:
        assert r["cost"] == {"usd": 0.0, "source": "rejudged", "window": None}
        assert r["rejudged"]["from_dataset_version"] == "v1" and r["rejudged"]["reason"] == REASON
        assert r["rejudged"]["previous"]["cost"]["usd"] == pytest.approx(0.001)
    assert by_id[right_id]["rejudged"]["previous"]["reject_reason"].startswith("rejected_by_oracle")
    assert by_id[wrong_id]["rejudged"]["previous"]["label"] == LABEL

    assert summary["teacher_calls"] == 0
    assert summary["control"] == {"judged_again": ADMITTED - 2, "changed": 0}
    assert sum(summary["verdict_changes"].values()) == 2
    # as generated: permutations 3 accepted (one wrong answer), graph states 4. Unchanged in number,
    # but now it is the RIGHT three permutations.
    assert summary["accepted_per_family"] == {"graph_state": ADMITTED, "qubit_permutation": 3}
    meta = json.loads((tmp_path / "v2" / "dataset_meta.json").read_text(encoding="utf-8"))
    source_meta = json.loads((source / "dataset_meta.json").read_text(encoding="utf-8"))
    assert meta["dataset_version"] == "v2" and meta["identity"] == source_meta["identity"]
    assert meta["derived_from"]["records_sha256"] == hashlib.sha256(before).hexdigest()
    copied = (tmp_path / "v2" / "registry.jsonl").read_bytes()
    assert copied == (source / "registry.jsonl").read_bytes()


def test_a_control_answer_that_changes_verdict_stops_everything(pool, tmp_path) -> None:
    source = _source(tmp_path, pool)
    _file_wrong_verdicts(source)
    with pytest.raises(RejudgeRefused, match="control"):
        # only variation 0 is selected: variation 1 (filed as accepted, really wrong) is now control
        _rejudge(source, tmp_path / "v2", pool, selects=lambda family, v: v.index == 0)
    assert not (tmp_path / "v2").exists()


def test_refusals_that_need_no_judging(pool, tmp_path) -> None:
    source = _source(tmp_path, pool)
    with pytest.raises(RejudgeRefused, match="new dataset version"):
        _rejudge(source, tmp_path / "v2", pool, dataset_version="v1")
    with pytest.raises(RejudgeRefused, match="no reason"):
        _rejudge(source, tmp_path / "v2", pool, reason="  ")
    with pytest.raises(RejudgeRefused, match="matches no answer"):
        _rejudge(source, tmp_path / "v2", pool, selects=lambda family, v: False)
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "x").write_text("x")
    with pytest.raises(RejudgeRefused, match="not empty"):
        _rejudge(source, tmp_path / "taken", pool)
    assert not (tmp_path / "v2").exists()
