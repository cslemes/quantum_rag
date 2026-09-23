"""Local generator client — Ollama (research.md D10, D10b, D10c)."""

import subprocess
import time
from typing import TypedDict

import httpx

from qcagent.llm.base import BaseLLMClient, LLMResponse, TransientProviderError

# HTTP statuses treated as transient — retried by BaseLLMClient.generate()
# with backoff before surfacing as InfrastructureError (T012b).
_TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class ContextOverflowError(Exception):
    """Raised when the prompt would meet or exceed `num_ctx`.

    Silent truncation must never happen on the experimental path (D10b):
    Ollama's own default context (4096) truncates without error or log, and
    the failure is selective — it hits condition C5 (RAG, the longest
    prompts) while leaving C1 untouched, which would invalidate H1/H3
    without leaving evidence in the results.
    """


class GPUOffloadError(Exception):
    """Raised when the local generator is not fully offloaded to GPU.

    Silent CPU/GPU offload makes throughput non-reproducible (D10c): a run
    with the desktop busy has less free VRAM than one without, and if the
    threshold is crossed mid-experiment, latency stops being comparable
    across executions. Better to fail loudly than contaminate the metric.
    """


class GPUTelemetry(TypedDict):
    gpu_memory_used_mib: int | None
    gpu_processor: str | None


def gpu_telemetry(model_id: str) -> GPUTelemetry:
    """Best-effort GPU memory usage (`nvidia-smi`) and offload status
    (`ollama ps`) for `model_id`, for recording on RunRecord (D10c).

    Returns None values, rather than raising, when nvidia-smi/ollama aren't
    available — e.g. running validators-only in an environment without a
    GPU. Callers on the experimental path should treat a None
    `gpu_processor` as untrusted (see `assert_full_gpu_offload`).
    """
    gpu_memory_used_mib: int | None = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        gpu_memory_used_mib = int(result.stdout.strip().splitlines()[0])
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        ValueError,
        IndexError,
    ):
        pass

    gpu_processor: str | None = None
    try:
        result = subprocess.run(
            ["ollama", "ps"], capture_output=True, text=True, timeout=5, check=True
        )
        gpu_processor = _parse_ollama_ps_processor(result.stdout, model_id)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    return {"gpu_memory_used_mib": gpu_memory_used_mib, "gpu_processor": gpu_processor}


def _parse_ollama_ps_processor(output: str, model_id: str) -> str | None:
    """Extracts the PROCESSOR column (e.g. "100% GPU", "67%/33% CPU/GPU")
    for `model_id`'s row in `ollama ps`'s tabwriter-aligned plain-text
    output. There is no JSON output mode for `ollama ps` as of the version
    this was written against — verify column alignment still holds if the
    installed ollama version differs (same caution as contracts/retrieval.md
    about verifying the pinned dependency's actual API).
    """
    lines = output.strip().splitlines()
    if len(lines) < 2:
        return None
    header = lines[0]
    col_start = header.find("PROCESSOR")
    if col_start == -1:
        return None
    col_end = header.find("UNTIL")

    for line in lines[1:]:
        if not line.strip():
            continue
        row_model = line.split()[0]
        if row_model != model_id:
            continue
        segment = line[col_start:col_end] if col_end != -1 else line[col_start:]
        return segment.strip()
    return None


def gpu_offload_fraction(base_url: str, model_id: str) -> float | None:
    """Share of the model resident in VRAM, from the HTTP API, or None when
    the model is not loaded.

    The CLI-based `gpu_telemetry` below cannot answer this from where this
    code actually runs: `ollama` and `nvidia-smi` are on the Windows host,
    and the agent reaches Ollama only over HTTP. That is why
    `RunRecord.gpu_processor` is None in every record ever written while
    data-model.md claimed a guard aborted on anything but "100% GPU" (F21).
    `/api/ps` reports `size` and `size_vram`, which is the same quantity the
    PROCESSOR column summarises.
    """
    try:
        response = httpx.get(f"{base_url}/api/ps", timeout=10)
        response.raise_for_status()
        for model in response.json().get("models", []):
            if model.get("name") == model_id or model.get("model") == model_id:
                size = model.get("size") or 0
                return (model.get("size_vram") or 0) / size if size else None
    except (httpx.HTTPError, ValueError, ZeroDivisionError):
        return None
    return None


def assert_full_gpu_offload_http(base_url: str, model_id: str) -> float:
    """D10c, enforced over HTTP. Raises unless the model is fully in VRAM.

    An offloaded run makes the latency figures meaningless, and SC-007 is a
    latency figure. Returns the measured fraction so the caller can record
    it: a guard whose result is not recorded is only half a guard, which is
    the F21 pattern this is fixing.
    """
    fraction = gpu_offload_fraction(base_url, model_id)
    if fraction is None:
        raise GPUOffloadError(
            f"cannot determine GPU offload for {model_id!r} — the model is not loaded at "
            f"{base_url}, so `/api/ps` reports nothing. Load it before checking."
        )
    if fraction < 1.0:
        raise GPUOffloadError(
            f"{model_id!r} is only {fraction:.0%} in VRAM; aborting rather than silently "
            "contaminating the latency metric that SC-007 is measured on (D10c)"
        )
    return fraction


def assert_full_gpu_offload(model_id: str) -> None:
    """Raises `GPUOffloadError` unless `model_id` is running 100% on GPU.
    Call before the local arm of the experimental matrix (D10c, T015c)."""
    telemetry = gpu_telemetry(model_id)
    processor = telemetry["gpu_processor"]
    if processor != "100% GPU":
        raise GPUOffloadError(
            f"{model_id!r} is not fully GPU-offloaded (PROCESSOR={processor!r} "
            "per `ollama ps`); aborting rather than silently contaminating "
            "the local-arm latency metric (D10c)"
        )


def ollama_version(base_url: str) -> str:
    """The running Ollama server's version, for `RunRecord.lib_versions`.

    Ollama now runs on the host (see docker-compose.yml / research.md's
    "Ambiente de execução canônico"), not as a version-pinned container
    image alongside the rest of the stack — nothing else fixes which build
    a given run actually talked to, and Principle II requires it recorded.
    Queried live via `GET /api/version` rather than `ollama --version`
    (subprocess) since the CLI isn't installed inside the app container;
    only the HTTP server is reachable, over `host.docker.internal`.

    Returns "unknown" rather than raising if the server is unreachable —
    same soft-fallback pattern as `config.git_sha()`: a run recorded with
    "unknown" here isn't reproducible and must not be cited as one, but a
    telemetry query failing shouldn't crash the run itself.
    """
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/version", timeout=5.0)
        response.raise_for_status()
        return str(response.json().get("version", "unknown"))
    except (httpx.HTTPError, ValueError):
        return "unknown"


class OllamaClient(BaseLLMClient):
    def __init__(
        self,
        base_url: str,
        model_id: str = "qwen2.5-coder:7b",
        num_ctx: int = 16384,
        temperature: float = 0.0,
        keep_alive: str = "60m",
    ) -> None:
        self.model_id = model_id
        self.base_url = base_url.rstrip("/")
        # Set explicitly on every request body below — never relies on the
        # Ollama server's own default context length (D10b).
        self.num_ctx = num_ctx
        self.temperature = temperature
        self.keep_alive = keep_alive
        self._client = httpx.Client(base_url=self.base_url, timeout=300.0)

    def count_tokens(self, text: str) -> int:
        """Conservative pre-flight estimate (~4 chars/token). Deliberately
        approximate and biased to over-count, so the anti-truncation guard
        fails safe rather than silently under-estimating. The authoritative
        count for RunRecord is `prompt_eval_count` from the response, used
        in `_generate_impl` below — this method is only for the guard.
        """
        return max(1, len(text) // 4)

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:
        estimated = self.count_tokens(system) + self.count_tokens(prompt)
        if estimated >= self.num_ctx:
            raise ContextOverflowError(
                f"prompt (~{estimated} tokens estimated) meets or exceeds "
                f"num_ctx={self.num_ctx}; refusing to send rather than let "
                "Ollama truncate it silently (D10b)"
            )

        start = time.perf_counter()
        try:
            response = self._client.post(
                "/api/chat",
                json={
                    "model": self.model_id,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    # Hold the model resident for the whole suite. Ollama's
                    # default unloads it after ~5 min idle, and a mid-run
                    # reload changes the engine state that generation turns
                    # out to depend on (F19). Explicit for the same reason
                    # `num_ctx` and `temperature` are: an inherited default
                    # that alters the measurement must never be inherited.
                    "keep_alive": self.keep_alive,
                    "options": {
                        "num_ctx": self.num_ctx,
                        "seed": seed,
                        "num_predict": max_tokens,
                        # Pinned for the same reason D10b pins `num_ctx`:
                        # never inherit a sampling parameter from the server
                        # or the model's Modelfile, because the default is
                        # invisible and changes the measurement.
                        #
                        # A seed ALONE does not make Ollama deterministic.
                        # Measured directly: same prompt, same seed, four
                        # calls -> two distinct outputs; adding
                        # temperature=0 -> four identical. Across the first
                        # two full suite runs this produced DIFFERENT
                        # attempt-1 output for 26.1% of (task, seed) pairs,
                        # which made a before/after comparison impossible:
                        # `compila@1` moved 10.9% -> 15.6% between two runs
                        # whose difference cannot affect attempt 1 at all.
                        # See F15.
                        "temperature": self.temperature,
                    },
                },
            )
            if response.status_code in _TRANSIENT_STATUS_CODES:
                raise TransientProviderError(
                    f"HTTP {response.status_code} from Ollama: {response.text[:200]}"
                )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise TransientProviderError(str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            # Not transient — retrying a 404/400 five times with backoff
            # just delays a config error by ~30s. httpx's default message
            # drops the response body, which is where Ollama actually says
            # what's wrong (most commonly: the model was never pulled), so
            # re-raise with it attached instead of letting this propagate
            # as a bare HTTPStatusError.
            raise RuntimeError(
                f"Ollama returned HTTP {exc.response.status_code} for model "
                f"{self.model_id!r}: {exc.response.text[:500]!r}. Not retried — this "
                f"is a real bug, per BaseLLMClient._generate_impl's contract, not a "
                f"transient failure. A 404 here usually means the model hasn't been "
                f"pulled yet: run `ollama pull {self.model_id}`."
            ) from exc
        data = response.json()
        latency_s = time.perf_counter() - start

        # prompt_eval_count/eval_count are Ollama's own accounting and are
        # the authoritative token counts — preferred over count_tokens()'s
        # pre-flight estimate for what actually gets recorded (T011c).
        input_tokens = data.get("prompt_eval_count", estimated)
        output_tokens = data.get("eval_count", 0)

        return LLMResponse(
            text=data["message"]["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,  # local inference — no monetary cost
            latency_s=latency_s,
            model_id=self.model_id,
            num_ctx=self.num_ctx,
        )
