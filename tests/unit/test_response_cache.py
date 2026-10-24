"""The response cache is keyed on everything the response depends on (F18).

The first run E was a replay of run C: the key held the model NAME, and the
server under that name had changed build. These tests pin the safe direction:
a change to anything that can alter the response is a cold miss, and a server
that cannot say what it is is not cached at all.
"""

import json
from pathlib import Path

import httpx
import pytest

from bench.runner import AccountingLLM, Usage, cache_use_summary
from qcagent.llm import base
from qcagent.llm.base import BaseLLMClient, LLMResponse
from qcagent.llm.ollama_client import OllamaClient


def _response(text: str = "x") -> LLMResponse:
    return LLMResponse(
        text=text, input_tokens=1, output_tokens=1, cost_usd=0.0, latency_s=0.0, model_id="m"
    )


class _Counting(BaseLLMClient):
    def __init__(self, cache_dir: Path, **attrs: object) -> None:
        self.model_id = "m"
        self.cache_dir = cache_dir
        self.impl_calls = 0
        for name, value in attrs.items():
            setattr(self, name, value)

    def _generate_impl(self, *, system: str, prompt: str, seed: int, max_tokens: int):
        self.impl_calls += 1
        return _response()

    def count_tokens(self, text: str) -> int:
        return len(text)


def _ask(client: BaseLLMClient, *, max_tokens: int = 100, seed: int = 1) -> None:
    client.generate(system="s", prompt="p", seed=seed, max_tokens=max_tokens)


def test_an_identical_request_is_served_from_the_cache_and_says_so(tmp_path: Path) -> None:
    client = _Counting(tmp_path)
    _ask(client)
    assert client.last_call_cache_hit is False
    _ask(client)
    assert client.last_call_cache_hit is True and client.impl_calls == 1


@pytest.mark.parametrize(
    "change",
    [
        {"temperature": 0.7},
        {"effort": "low"},
        {"num_ctx": 4096},
        {"send_temperature": True},
    ],
)
def test_a_sampling_parameter_in_the_key_makes_a_change_a_cold_miss(tmp_path, change) -> None:
    _ask(_Counting(tmp_path, temperature=0.0, effort="high", num_ctx=16384))
    other = _Counting(
        tmp_path, **{"temperature": 0.0, "effort": "high", "num_ctx": 16384, **change}
    )
    _ask(other)
    assert other.impl_calls == 1 and other.last_call_cache_hit is False


def test_max_tokens_and_seed_are_in_the_key(tmp_path: Path) -> None:
    client = _Counting(tmp_path)
    _ask(client, max_tokens=100)
    _ask(client, max_tokens=200)
    _ask(client, seed=2)
    assert client.impl_calls == 3


def _ollama(tmp_path: Path, *, version: str, digest: str = "d1", reachable: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        if not reachable:
            raise httpx.ConnectError("down")
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": version})
        return httpx.Response(200, json={"models": [{"name": "m", "model": "m", "digest": digest}]})

    client = OllamaClient("http://x", "m", 16384, 0.0)
    client._client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x")
    client.cache_dir = tmp_path
    calls: list[int] = []

    def impl(*, system, prompt, seed, max_tokens):
        calls.append(1)
        return _response()

    client._generate_impl = impl  # type: ignore[method-assign]
    return client, calls


def test_a_server_build_change_is_a_cold_miss_not_a_replay(tmp_path: Path) -> None:
    """The first run E, in miniature: same model name, same prompt, new build."""
    old, old_calls = _ollama(tmp_path, version="0.35.1")
    _ask(old)
    new, new_calls = _ollama(tmp_path, version="0.40.8")
    _ask(new)
    assert len(old_calls) == 1 and len(new_calls) == 1 and new.last_call_cache_hit is False
    again, again_calls = _ollama(tmp_path, version="0.40.8")
    _ask(again)
    assert again_calls == [] and again.last_call_cache_hit is True


def test_a_repulled_model_under_the_same_name_is_a_cold_miss(tmp_path: Path) -> None:
    first, _ = _ollama(tmp_path, version="0.40.8", digest="aaa")
    _ask(first)
    repulled, calls = _ollama(tmp_path, version="0.40.8", digest="bbb")
    _ask(repulled)
    assert len(calls) == 1 and repulled.last_call_cache_hit is False


def test_a_server_that_cannot_say_what_it_is_is_not_cached(tmp_path: Path) -> None:
    client, calls = _ollama(tmp_path, version="0.40.8", reachable=False)
    _ask(client)
    _ask(client)
    assert len(calls) == 2 and not list(tmp_path.glob("*.json"))


def test_accounting_counts_hits_per_run(tmp_path: Path) -> None:
    usage = Usage()
    llm = AccountingLLM(_Counting(tmp_path), usage)
    llm.generate(system="s", prompt="p", seed=1)
    llm.generate(system="s", prompt="p", seed=1)
    llm.generate(system="s", prompt="q", seed=1)
    assert (usage.calls, usage.cache_hits) == (3, 1)
    usage.reset()
    assert (usage.calls, usage.cache_hits) == (0, 0)


def test_a_hit_on_an_entry_this_process_wrote_is_a_self_hit(tmp_path: Path) -> None:
    usage = Usage()
    llm = AccountingLLM(_Counting(tmp_path), usage)
    llm.generate(system="s", prompt="p", seed=1)
    llm.generate(system="s", prompt="p", seed=1)
    assert (usage.cache_hits, usage.cache_hits_preexisting) == (1, 0)


def test_a_hit_on_an_entry_from_before_the_process_is_pre_existing(tmp_path: Path) -> None:
    _Counting(tmp_path).generate(system="s", prompt="p", seed=1)
    # Another process's entry is one this process never wrote.
    base._WRITTEN_THIS_PROCESS.discard((tmp_path / next(tmp_path.glob("*.json")).name).resolve())
    usage = Usage()
    llm = AccountingLLM(_Counting(tmp_path), usage)
    llm.generate(system="s", prompt="p", seed=1)
    llm.generate(system="s", prompt="p", seed=1)
    # The first hit is the replay; once served, it is still not this run's entry.
    assert (usage.cache_hits, usage.cache_hits_preexisting) == (2, 2)


def _jsonl(tmp_path: Path, rows: list[tuple[int, ...]]) -> Path:
    """Rows are (calls, hits) or (calls, hits, pre-existing hits)."""
    path = tmp_path / "runs.jsonl"
    records = []
    for row in rows:
        record = {"llm_calls": row[0], "cache_hits": row[1]}
        if len(row) == 3:
            record["cache_hits_preexisting"] = row[2]
        records.append(json.dumps(record))
    path.write_text("\n".join(records) + "\n")
    return path


@pytest.mark.parametrize(
    "rows,word",
    [
        ([(10, 0), (10, 0)], "COLD"),
        ([(10, 10), (10, 9)], "REPLAY"),
        ([(10, 5), (10, 0)], "PARTLY WARM"),
        ([(0, 0)], "NO GENERATOR CALLS"),
        # Run G's shape: hits, all of them on entries the run wrote itself.
        ([(10, 5, 0), (10, 4, 0)], "COLD"),
        ([(10, 10, 9), (10, 9, 9)], "REPLAY"),
        ([(10, 6, 2), (10, 0, 0)], "PARTLY WARM"),
    ],
)
def test_cache_summary_names_a_cold_a_warm_and_a_replayed_run(tmp_path, rows, word) -> None:
    assert word in str(cache_use_summary(_jsonl(tmp_path, rows))["verdict"])


def test_summary_reports_both_numbers_and_decides_on_pre_existing_only(tmp_path: Path) -> None:
    summary = cache_use_summary(_jsonl(tmp_path, [(10, 5, 0), (10, 4, 1)]))
    assert (summary["cache_hits"], summary["cache_hits_preexisting"]) == (9, 1)
    assert summary["cache_hits_self"] == 8 and "PARTLY WARM" in str(summary["verdict"])


def test_a_record_without_the_split_counts_all_its_hits_as_pre_existing(tmp_path: Path) -> None:
    summary = cache_use_summary(_jsonl(tmp_path, [(10, 3)]))
    assert summary["cache_hits_preexisting"] == 3
