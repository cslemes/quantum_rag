"""Common generator interface: token counting, cost accounting, response
caching (FR-028), and retry for transient provider failures.

Concrete clients (anthropic_client.py, ollama_client.py) implement
`BaseLLMClient._generate_impl` and `count_tokens`. Everything else —
caching, retry/backoff, and the resulting `InfrastructureError` — lives here
so it applies uniformly to every provider.
"""

import hashlib
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

CACHE_DIR = Path(".cache/llm")


class LLMResponse(BaseModel):
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_s: float
    model_id: str
    # Effective context window used for this call. Only meaningful for
    # providers with a configurable context window (Ollama); left as None by
    # providers where the concept doesn't apply (Anthropic). Threaded through
    # to RunRecord so the *effective* value is in the result, not only in
    # config (tasks.md T011c).
    num_ctx: int | None = None
    # What actually served the call (qcagent.llm.provenance): None for clients
    # that do not record it. Stored in the cache entry with the response, so a
    # cache hit reports the provenance of the call that produced it.
    provenance: dict[str, Any] | None = None


class TransientProviderError(Exception):
    """Raised by `_generate_impl` implementations for a transient failure —
    rate limit, 5xx, timeout/connection error. Retried by `generate` with
    exponential backoff; see `InfrastructureError` for what happens once
    retries are exhausted.

    Anything else raised by `_generate_impl` is treated as a real bug and
    propagates immediately, uncaught.
    """


class InfrastructureError(Exception):
    """Raised when a `TransientProviderError` survives all retries.

    Callers must record this as `status="infrastructure_error"` and must
    NOT route it through the critic — it is not an `error_type` of
    generated code (spec edge case, tasks.md T012b).
    """


class BaseLLMClient(ABC):
    """Template method: subclasses implement `_generate_impl` and pricing;
    `generate` is the public entry point, wrapping `_generate_impl` with a
    disk-backed response cache and bounded retry.
    """

    model_id: str
    cache_dir: Path = CACHE_DIR
    # Whether the LAST `generate` call was answered from the disk cache. The
    # accounting wrapper reads it so a run can say how much of it was replayed:
    # a replay that nothing reports looks exactly like a measurement.
    last_call_cache_hit: bool = False

    # Attributes, when present on the client, that change what it returns. They
    # go into the cache key (see `response_identity`).
    _IDENTITY_ATTRS = (
        "effort",
        "provider",
        "send_temperature",
        "temperature",
        "headroom",
        "thinking_headroom",
        "num_ctx",
        "provider_options",
        "_base_url",
    )

    @abstractmethod
    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        """Provider-specific call. Raise `TransientProviderError` for
        rate-limit/5xx/timeout failures; anything else is a real bug."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Provider-specific token count, used for pre-flight context checks
        (see ollama_client.py's anti-truncation guard, T011b)."""

    def generate(
        self, *, system: str, prompt: str, seed: int, max_tokens: int = 4096
    ) -> LLMResponse:
        self.last_call_cache_hit = False
        identity = self.response_identity()
        # None means the identity could not be established (a server that
        # cannot be asked what it is): the cache is then neither read nor
        # written, since a key built on a guess is how a wrong hit happens.
        key = (
            None
            if identity is None
            else self._cache_key(
                system=system, prompt=prompt, seed=seed, max_tokens=max_tokens, identity=identity
            )
        )
        if key is not None:
            cached = self._cache_load(key)
            if cached is not None:
                self.last_call_cache_hit = True
                return cached

        response = self._generate_with_retry(
            system=system, prompt=prompt, seed=seed, max_tokens=max_tokens
        )
        if key is not None:
            self._cache_save(key, response)
        return response

    def response_identity(self) -> dict[str, str] | None:
        """Everything, besides system/prompt/seed/max_tokens, that the response
        depends on: the client, the model, and the sampling/routing attributes
        it was built with. Subclasses that talk to a server whose build or
        model file can change under the same name add those (OllamaClient adds
        the server version and the resolved model digest).

        Anything that can change the response and is absent here is a
        silent-replay path (F18): a change then produces a WRONG HIT, where
        including it produces a cold miss, which is safe.
        """
        identity = {"client": type(self).__name__, "model": self.model_id}
        for attr in self._IDENTITY_ATTRS:
            value = getattr(self, attr, None)
            if value is not None:
                identity[attr.lstrip("_")] = str(value)
        return identity

    def _generate_with_retry(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(5),
                wait=wait_exponential(multiplier=1, min=1, max=30),
                retry=retry_if_exception_type(TransientProviderError),
                reraise=True,
            ):
                with attempt:
                    return self._generate_impl(
                        system=system, prompt=prompt, seed=seed, max_tokens=max_tokens
                    )
        except TransientProviderError as exc:
            raise InfrastructureError(f"exhausted retries calling {self.model_id}: {exc}") from exc
        raise AssertionError("unreachable — Retrying always returns or raises")

    # -- Response cache (FR-028) ------------------------------------------
    #
    # Keyed by hash(everything the response depends on): the request (system,
    # prompt, seed, max_tokens) AND the identity of what answers it (model,
    # resolved digest, server build, sampling parameters — `response_identity`).
    # Re-running an identical attempt against the identical system (e.g.
    # resuming an interrupted matrix run, T054b) never re-pays for analysis
    # already done; any change to the system is a cold miss, not a replay.

    def _cache_key(
        self, *, system: str, prompt: str, seed: int, max_tokens: int, identity: dict[str, str]
    ) -> str:
        raw = json.dumps(
            {
                "identity": identity,
                "seed": seed,
                "max_tokens": max_tokens,
                "system": system,
                "prompt": prompt,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _cache_load(self, key: str) -> LLMResponse | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        return LLMResponse.model_validate_json(path.read_text())

    def _cache_save(self, key: str, response: LLMResponse) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(key).write_text(json.dumps(response.model_dump()))
