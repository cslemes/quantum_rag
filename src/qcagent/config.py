"""Application settings, structured logging, and run identification.

See .env.example for the full list of settings variables.
"""

import hashlib
import importlib.metadata
import json
import logging
import multiprocessing
import os
import platform
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import structlog
from pydantic_settings import BaseSettings, SettingsConfigDict

from qcagent.llm.ollama_client import ollama_version


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Fronteira A (research.md D10)
    anthropic_api_key: str | None = None
    fronteira_a_model: str = "claude-sonnet-4-5"

    # Fronteira B — distinct model family, provider-agnostic (D10)
    fronteira_b_api_key: str | None = None
    fronteira_b_base_url: str | None = None
    fronteira_b_model: str | None = None

    # Local generator (D10, D10b)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"
    ollama_num_ctx: int = 16384
    # Pinned, never inherited from the model's Modelfile (F15, generalizing
    # D10b's rule for num_ctx). A seed alone does NOT make Ollama
    # deterministic: two full suite runs disagreed on attempt 1 for 26.1% of
    # (task, seed) pairs, which made before/after comparison impossible.
    ollama_temperature: float = 0.0

    # Qdrant (D5b)
    qdrant_url: str = "http://localhost:6333"

    # Agent loop (D8 — pilot hypothesis, validated in T056)
    max_iter: int = 5

    # Sandbox / WorkerPool (D1b, D11)
    sandbox_timeout_s: int = 60
    worker_pool_size: int = 6
    worker_recycle_after: int = 50

    results_dir: Path = Path("results")

    log_level: str = "INFO"


settings = Settings()


def configure_logging(level: str | None = None) -> None:
    """Structured (JSON-renderable) logging. Call once at process start."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, (level or settings.log_level).upper())
        ),
    )


def git_sha() -> str:
    """Current commit SHA, or "unknown" outside a git repo / without git
    installed.

    Reproducibility (Principio II) needs the real SHA. A run recorded with
    "unknown" is not reproducible and must not be treated as a citable
    result — this is a soft fallback so the code doesn't crash, not a
    substitute for actually running from a git checkout.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return result.stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"


def make_run_id(config: dict, *, sha: str | None = None, timestamp: str | None = None) -> str:
    """run_id = hash(config + git SHA + timestamp) — FR-026.

    `sha`/`timestamp` are overridable for testing; in production code, leave
    them unset so the real git SHA and current time are used.
    """
    resolved_sha = sha if sha is not None else git_sha()
    resolved_timestamp = timestamp if timestamp is not None else datetime.now(UTC).isoformat()
    payload = json.dumps(
        {"config": config, "git_sha": resolved_sha, "timestamp": resolved_timestamp},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# Every dependency whose exact version could change the result: the pinned
# simulation/verification stack (Principle II) plus the frameworks the
# agent loop and retrieval depend on. Read via importlib.metadata — the
# *installed* version, not what pyproject.toml asks for, so a `uv.lock`
# drift shows up in the recorded run instead of being silently assumed.
_TRACKED_PACKAGES = (
    "qiskit",
    "qiskit-aer",
    "pennylane",
    "langgraph",
    "qdrant-client",
    "fastembed",
    "anthropic",
)


def collect_lib_versions(*, ollama_base_url: str | None = None) -> dict[str, str]:
    """Populates `RunRecord.lib_versions` (Principle II).

    Ollama is the one entry NOT read from installed-package metadata: since
    research.md's canonical environment moved it out of docker-compose and
    onto the host (it's a server the app talks to over HTTP, not a Python
    dependency), nothing else pins which build a given run actually talked
    to. Queried live via `ollama_version()` instead.
    """
    versions: dict[str, str] = {}
    for package in _TRACKED_PACKAGES:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unknown"
    versions["ollama"] = ollama_version(ollama_base_url or settings.ollama_base_url)
    # The GPU stack (driver + CUDA runtime) changes generation output across an
    # upgrade or another machine, and NOTHING here can observe it: the GPU
    # belongs to the host, `nvidia-smi` is not in this container, and Ollama's
    # API exposes neither. So it is declared by the operator rather than
    # detected, and its absence is recorded as absence instead of being
    # silently omitted — a field that is missing from the record cannot be
    # distinguished later from a field that was checked and matched.
    versions["gpu_stack"] = os.environ.get("QCAGENT_GPU_STACK", "unrecorded")
    versions.update(environment_identity())
    return versions


def environment_identity() -> dict[str, str]:
    """WHERE this ran, which was the largest unrecorded condition of all.

    D15 declared the agent ran in a container. It never did — every number in
    this project came from a venv on the host, and the records could not
    reveal that, because nothing captured the environment. "Where did this
    run?" was answerable only from the memory of whoever ran it.

    Verification runs locally (`Statevector`, `Operator.equiv()`, tolerance
    comparisons), so a different BLAS or CPU dispatch can flip a verdict at a
    tolerance boundary. That makes the environment a controlled condition in
    exactly the sense `ollama_temperature` and `qdocs_points` are, not
    metadata.
    """
    identity = {
        "hostname": socket.gethostname(),
        "python": sys.executable,
        "platform": f"{platform.system()} {platform.release()}",
        "mp_start_method": multiprocessing.get_start_method(),
        # D15's substantive requirement is Linux + fork, never Windows spawn.
        # Recorded so the claim is checkable rather than assumed.
        "containerized": "yes" if Path("/.dockerenv").exists() else "no",
    }
    # Set by the image build so a containerized run identifies WHICH image.
    if digest := os.environ.get("QCAGENT_IMAGE_DIGEST"):
        identity["image_digest"] = digest
    return identity
