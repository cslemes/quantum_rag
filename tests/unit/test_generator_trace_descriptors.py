"""The trace records a hash of each attempt's code, how it was extracted and how many
tokens it took. Additive: the extracted code itself is unchanged."""

from __future__ import annotations

import hashlib

from qcagent.llm.base import LLMResponse
from qcagent.nodes.generator import _attempt_descriptors, _extract_code, make_generator_node


class _Fake:
    def __init__(self, text: str, output_tokens: int = 7) -> None:
        self.text, self.output_tokens = text, output_tokens

    def generate(self, *, system: str, prompt: str, seed: int, max_tokens: int) -> LLMResponse:
        return LLMResponse(
            text=self.text,
            input_tokens=1,
            output_tokens=self.output_tokens,
            cost_usd=0.0,
            latency_s=0.0,
            model_id="m",
        )


def _run(text: str, tokens: int = 7) -> dict:
    node = make_generator_node(_Fake(text, tokens))  # type: ignore[arg-type]
    return node({"requirements": [], "iteration": 0, "error_history": []})  # type: ignore[arg-type]


def test_a_closed_fence_is_extracted_and_hashed() -> None:
    update = _run("```python\nqc = 1\n```", 12)
    entry = update["trace"][0]
    assert update["code"] == "qc = 1"
    assert entry["code_extraction"] == "fenced" and entry["output_tokens"] == 12
    assert entry["code_sha256_16"] == hashlib.sha256(b"qc = 1").hexdigest()[:16]


def test_an_unclosed_fence_is_recorded_as_a_raw_fallback_and_behaves_as_before() -> None:
    text = "```python\nqc = 1\n# Apply the oracle one more"
    update = _run(text, 4096)
    assert update["code"] == _extract_code(text) == text.strip()  # unchanged behaviour
    assert update["trace"][0]["code_extraction"] == "raw_fallback"
    assert update["trace"][0]["output_tokens"] == 4096


def test_identical_code_has_identical_hash_and_different_code_does_not() -> None:
    a, b, c = (_attempt_descriptors(t, _extract_code(t), 1) for t in ("x = 1", "x = 1", "x = 2"))
    assert a["code_sha256_16"] == b["code_sha256_16"] != c["code_sha256_16"]


# -- a truncated generation is its own condition ----------------------------------


def test_cap_hit_without_a_closing_fence_is_truncation() -> None:
    from qcagent.nodes.generator import GENERATION_MAX_TOKENS, is_truncated

    cut = "```python\nqc = 1\n# Apply the oracle one more"
    assert is_truncated(cut, GENERATION_MAX_TOKENS)
    assert not is_truncated(cut, GENERATION_MAX_TOKENS - 1)  # ended on its own: as before
    assert not is_truncated("```python\nqc = 1\n```", GENERATION_MAX_TOKENS)  # closed
    assert not is_truncated("qc = 1", 10)  # bare code that finished is still extracted


def test_the_generator_flags_truncation_in_state_and_trace() -> None:
    from qcagent.nodes.generator import GENERATION_MAX_TOKENS

    update = _run("```python\nqc = 1\n# and so on and so on", GENERATION_MAX_TOKENS)
    assert update["generation_truncated"] is True
    assert update["trace"][0]["generation_truncated"] is True
    ok = _run("```python\nqc = 1\n```", 12)
    assert ok["generation_truncated"] is False


def test_static_check_reports_generation_truncated_without_executing() -> None:
    from qcagent.graph import make_static_check_node

    class _Pool:
        def submit(self, *a, **k):
            raise AssertionError("a truncated generation must not be executed")

    node = make_static_check_node(_Pool())  # type: ignore[arg-type]
    update = node(
        {"code": "```python\nqc = 1\n# cut", "generation_truncated": True, "iteration": 3}
    )
    error = update["static"].error
    assert error.error_type == "GenerationTruncated" and error.iteration == 3
    assert update["static"].executed is False and update["error_history"] == [error]


def test_a_truncated_generation_routes_to_retry_generation() -> None:
    from qcagent.nodes.critic import route_action
    from qcagent.state import ErrorRecord, StaticResult

    static = StaticResult(
        parsed=False,
        executed=False,
        transpiled=False,
        error=ErrorRecord(
            iteration=1, stage="static", error_type="GenerationTruncated", message="x"
        ),
    )
    assert route_action(static, None, None, None, 1, 5, [])[0] == "retry_generation"
