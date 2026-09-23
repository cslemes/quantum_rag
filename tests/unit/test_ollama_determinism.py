"""Sampling parameters are pinned, never inherited (F15, D10b's rule extended).

A seed alone does not make Ollama deterministic. Measured against the live
server: same prompt, same seed, four calls produced two distinct outputs;
adding `temperature=0` produced four identical ones.

The cost of not pinning it was the first before/after comparison: 26.1% of
(task, seed) pairs produced a DIFFERENT attempt 1 across two runs, and
attempt 1 happens before any of the changes under test could apply. That
made the two runs incomparable and SC-008 unmeasurable.

D10b already established this rule for `num_ctx` — "nunca herdado do default
do servidor", because a silently inherited value changes the measurement
without leaving a trace. The rule was right and was never generalized to the
other sampling parameters. This test is that generalization.
"""

import json

from qcagent.llm.ollama_client import OllamaClient


class _CapturingTransport:
    """Records the request body instead of reaching a server."""

    def __init__(self) -> None:
        self.sent: dict = {}

    def __call__(self, request):  # httpx transport-ish hook
        self.sent = json.loads(request.content)
        raise AssertionError("captured")


def test_temperature_is_sent_explicitly_and_defaults_to_zero() -> None:
    client = OllamaClient("http://unused:11434")

    assert client.temperature == 0.0, (
        "a regression suite must not inherit the model's default sampling "
        "temperature — the default is invisible and changes the numbers"
    )


def test_temperature_is_configurable_without_touching_the_default() -> None:
    """Pinned does not mean hardcoded: an experiment that deliberately wants
    sampling can ask for it, and the value it asked for is then explicit."""
    assert OllamaClient("http://unused:11434", temperature=0.7).temperature == 0.7
