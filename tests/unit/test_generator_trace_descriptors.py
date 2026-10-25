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
