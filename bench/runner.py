"""Regression-suite runner (US7, T054/T098b/T099).

    uv run python -m bench.runner --config config.yaml        # or: make eval

Runs each configured (task, seed) through the real graph and appends one
`RunRecord` per run to `results/{run_id}/runs.jsonl`, append-only
(Principle III, FR-025/FR-026). This is a regression suite, not v1's
experimental matrix: one configuration per run, no condition axis.

**Principle IV is enforced here, at the point of use.** Before any task runs
— before the sandbox starts, before a single token is spent — every oracle
in the configuration is re-validated with `bench/validate_oracles.py`'s own
checks. One unverified reference aborts the WHOLE run, not just its own
task: a suite whose references aren't verified cannot produce a trustworthy
number about anything, and a partially-run suite invites reading the tasks
that did run. `make validate-oracles` in CI (T051) is the other half; this
half protects someone running the suite locally with no CI in the loop.
"""

import argparse
import json
import sys
import time
import traceback
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import yaml
from pydantic import BaseModel, Field, model_validator
from qdrant_client import QdrantClient

from bench.schema import RunRecord, TaskSpec
from bench.validate_oracles import validate_one
from qcagent.config import collect_lib_versions, git_sha, make_run_id, settings
from qcagent.graph import Oracle, recursion_limit_for
from qcagent.live import LiveServices, build_live_graph, initial_state
from qcagent.llm.base import BaseLLMClient, LLMResponse
from qcagent.llm.ollama_client import (
    GPUOffloadError,
    OllamaClient,
    assert_full_gpu_offload_http,
    gpu_offload_fraction,
)
from qcagent.retrieval.embedding import FastEmbedEmbedder
from qcagent.state import AgentState, ErrorRecord
from qcagent.validators.sandbox import WorkerPool

TASKS_DIR = Path("bench/tasks")


class UnverifiedReferenceError(RuntimeError):
    """Raised when any configured task's oracle fails validation. Carries
    every failure, not just the first: a maintainer fixing references wants
    the whole list, and stopping at the first hides the scale."""


class ProtocolIntegrityError(RuntimeError):
    """Raised when the protocol canary's seeds diverge — see
    RunConfig.protocol_canary."""


class RunConfig(BaseModel):
    """`config.yaml` — the source of truth for one regression run."""

    model: str = Field(default_factory=lambda: settings.ollama_model)
    # Which API serves `model`. "anthropic" is the frontier arm: it answers
    # "is the bottleneck the architecture or the generator?" with every LLM
    # role (planner, generator, critic) served by the frontier model and
    # everything else — corpus, validators, routing, corrector — unchanged.
    provider: Literal["ollama", "anthropic", "openrouter", "groq", "openai"] = "ollama"
    # OpenAI only: send temperature=0 (qwen parity). Off unless a probe showed
    # the model accepts it — reasoning models commonly reject it.
    send_temperature: bool = False
    # OpenRouter only: the reasoning effort sent with every call. A config
    # field, not a constant, because the reasoning-off arm exists to separate
    # model capability from the reasoning effect — the value must be in the
    # record and change the run_id.
    reasoning_effort: str = "high"
    # Ollama only: where the Ollama server is, overriding OLLAMA_BASE_URL.
    # The RunPod arm points this at an SSH tunnel (http://localhost:<port>)
    # to an Ollama bound to localhost inside the pod: generation remote,
    # verification local — the same split as the API arms, so the model is the
    # only variable. `generator_host` names where it ran, for the record.
    ollama_base_url: str | None = None
    generator_host: str = "local"
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    # Task ids to run, or "all" for every task under bench/tasks/.
    tasks: list[str] | str = "all"
    max_iter: int = Field(default_factory=lambda: settings.max_iter)
    results_dir: Path = Field(default_factory=lambda: settings.results_dir)
    # Unload the model before EVERY (task, seed), not once per suite (F28).
    # Ollama's prompt/KV cache carries state from one task to the next and
    # changes the answer at temperature 0, so without this a task's result
    # depends on which task ran before it: a change to task k moves k+1..N,
    # and a per-task comparison (analysis/compare.py) smears instead of
    # localizing. Costs one model load per run — the SC-007 amendment in
    # report-notes.md records that cost as a consequence of the protocol.
    # Part of the config, so it is recorded with the results and changes the
    # run_id.
    reset_per_run: bool = True
    # Protocol canary (F28, F29). Under reset_per_run the three seeds of a
    # task are byte-identical (16/16 in every arm of T114), which is why the
    # suite runs one seed. That identity is an INVARIANT of the protocol: if
    # cross-task contamination returns, or a server upgrade makes the seed
    # matter at temperature 0, seeds start to differ — and one seed stops
    # being a sample of anything. So it is checked before every suite, on a
    # few fast tasks, instead of paid for with 240 redundant runs (F11: a rule
    # that matters gets a mechanism, not a reminder).
    protocol_canary: list[str] = Field(
        default_factory=lambda: ["qaoa_maxcut_4q_perturbed", "dj_constant_4q"]
    )
    canary_seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])

    @model_validator(mode="after")
    def _ollama_only_protocol(self) -> "RunConfig":
        # The reset and the canary are about Ollama's server state (F28). The
        # Anthropic API is not deterministic and has no state to unload, so
        # a byte-identical canary would fail by construction, and a reset
        # would unload an unrelated local model. Stated in the config rather
        # than silently skipped, so the record says which protocol applied.
        if self.provider != "ollama" and (self.reset_per_run or self.protocol_canary):
            raise ValueError(
                f"provider {self.provider!r} requires reset_per_run: false and protocol_canary: [] "
                "— both are properties of the local Ollama server (F28)"
            )
        return self

    @property
    def ollama_url(self) -> str:
        return self.ollama_base_url or settings.ollama_base_url

    @classmethod
    def load(cls, path: Path) -> "RunConfig":
        return cls.model_validate(yaml.safe_load(path.read_text()) or {})


def load_tasks(config: RunConfig, tasks_dir: Path = TASKS_DIR) -> list[TaskSpec]:
    """Resolves the configuration's task ids to `TaskSpec`s. An id that
    matches no task file is an error, not an empty selection — a typo in
    `config.yaml` must not silently shrink the suite."""
    by_id = {
        spec.task_id: spec
        for spec in (
            TaskSpec.model_validate_json(p.read_text()) for p in sorted(tasks_dir.rglob("*.json"))
        )
    }
    if config.tasks == "all":
        return list(by_id.values())
    if isinstance(config.tasks, str):
        raise ValueError(f"tasks must be a list of task ids or 'all', got {config.tasks!r}")
    unknown = [t for t in config.tasks if t not in by_id]
    if unknown:
        raise ValueError(f"config names task ids that do not exist under {tasks_dir}/: {unknown}")
    return [by_id[t] for t in config.tasks]


def verify_references(tasks: Iterable[TaskSpec]) -> list[str]:
    """T099 — re-runs `validate_oracles.py`'s checks over exactly the
    configured tasks. Returns one message per FAILED check; empty means
    every reference in this run is verified. Deliberately re-runs the
    checks rather than trusting a stored verdict: a stored one can be
    stale, and the whole point is that the suite refuses to measure against
    a reference nobody just verified.
    """
    failures: list[str] = []
    for task in tasks:
        try:
            results = validate_one(task)
        except Exception as exc:  # noqa: BLE001 — a broken oracle file lands here
            failures.append(f"{task.task_id}: validation raised {type(exc).__name__}: {exc}")
            continue
        # `verdict is False` only: a check can return None for "N/A" (e.g. no
        # qiskit.circuit.library primitive exists for this family), and `not
        # verdict` would read that as a failure and block every run.
        failures.extend(
            f"{task.task_id}: {name} — {detail}"
            for name, verdict, detail in results
            if verdict is False
        )
    return failures


def verify_gpu_offload(base_url: str, model: str) -> float:
    """D10c: refuse to run unless the generator is fully on GPU.

    Ordering matters and is deliberate. This runs BEFORE
    `reset_generator_state`, because `/api/ps` can only report a model that
    is loaded, and the reset unloads it. Warming here and unloading after
    leaves the run starting from exactly the same cold state the 0/360
    determinism was measured under — the check is added without changing the
    protocol it would otherwise invalidate.

    The guard described in data-model.md had never executed: it shelled out
    to `ollama ps` and `nvidia-smi`, which live on the Windows host, so
    `gpu_processor` is None in all 360 records of every run ever made (F21).
    """
    if gpu_offload_fraction(base_url, model) is None:
        # Not loaded: warm it so there is something to measure. Safe to do
        # here precisely because the unload follows.
        try:
            httpx.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": "ok", "stream": False},
                timeout=300,
            )
        except httpx.HTTPError as exc:
            raise GPUOffloadError(f"could not reach the generator at {base_url}: {exc}") from exc
    fraction = assert_full_gpu_offload_http(base_url, model)
    print(f"generator offload: {fraction:.0%} GPU (D10c)", flush=True)
    return fraction


def reset_generator_state(base_url: str, model: str) -> None:
    """Unload the model, so the run starts from a known engine state.

    Generation turned out to depend on state INSIDE the inference server, not
    only on the request: an identical prompt (same seed, `temperature=0`) can
    return one answer computed fresh and a different one served off Ollama's
    own prompt/KV cache. Two suite runs back to back therefore differ — the
    second inherits the first's cache. It is F18's problem one level down: a
    memoization layer between the experiment and the system under test, except
    this one is not ours and cannot be deleted from disk.

    Unloading is the only handle the HTTP API gives us over that state. It
    does not prove determinism — that is what the two-run measurement is for
    (F19) — it removes one known way for two runs to start differently.
    """
    try:
        httpx.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
        time.sleep(3)  # the unload is asynchronous; give it a moment to land
        print(f"generator state reset: {model} unloaded before the run", flush=True)
    except httpx.HTTPError as exc:  # pragma: no cover - best effort, never fatal
        # A failed reset is worth saying out loud but must not abort a run:
        # the consequence is a possibly-warm start, which the comparison will
        # show, not a wrong result.
        print(f"WARNING: could not reset generator state ({exc})", file=sys.stderr, flush=True)


class EmptyIndexError(RuntimeError):
    """Raised when the retrieval collection is missing or empty."""


def require_populated_index(client: QdrantClient) -> int:
    """Refuse to start if there is nothing to retrieve — the same shape of
    precondition as Principle IV's reference check, checked once up front
    rather than discovered 360 times.

    Found the hard way: the `qdocs` collection was gone (its volume had been
    recreated), and every single run failed in the retriever. Containment
    meant the suite completed instead of crashing, which is worse in this
    one respect — it produced a full results file of uniform failures that
    looks like a measurement of the system. It is a measurement of a missing
    index.

    An EMPTY collection counts as missing. It exists, so `search()` is happy
    to return zero chunks, and the suite would then quietly measure the
    generator with no retrieval at all — a different system from the one
    under test, reported under the same name.
    """
    from qcagent.retrieval.index import COLLECTION

    if not client.collection_exists(COLLECTION):
        raise EmptyIndexError(
            f"collection {COLLECTION!r} does not exist — run `make index` before the suite. "
            "Refusing to start: every run would fail in the retriever and the results file "
            "would look like a measurement of the generator."
        )
    points = client.count(COLLECTION, exact=True).count
    if points == 0:
        raise EmptyIndexError(
            f"collection {COLLECTION!r} exists but is EMPTY — run `make index`. Refusing to "
            "start: retrieval would silently return nothing and the suite would measure a "
            "generator with no RAG, reported as though it had one."
        )
    print(f"retrieval index: {points} points in {COLLECTION!r}", flush=True)
    return points


@dataclass
class Usage:
    """What one run cost. The graph has no token/cost channel in its state
    (by design — that is measurement, not agent state), so accounting lives
    around the client every node shares."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0
    num_ctx: int | None = None

    def reset(self) -> None:
        self.input_tokens = self.output_tokens = self.calls = 0
        self.cost_usd = 0.0


class AccountingLLM(BaseLLMClient):
    """Passes every call through to the real client and totals it into
    `usage`. Wraps `generate` (not `_generate_impl`) so a cache hit — which
    costs nothing — is counted as the zero it is."""

    def __init__(self, inner: BaseLLMClient, usage: Usage) -> None:
        self.inner = inner
        self.usage = usage
        self.model_id = inner.model_id
        self.cache_dir = inner.cache_dir

    def count_tokens(self, text: str) -> int:
        return self.inner.count_tokens(text)

    def _generate_impl(
        self, *, system: str, prompt: str, seed: int, max_tokens: int
    ) -> LLMResponse:  # pragma: no cover - generate() below never delegates here
        raise AssertionError("unreachable — AccountingLLM overrides generate()")

    def generate(
        self, *, system: str, prompt: str, seed: int, max_tokens: int = 4096
    ) -> LLMResponse:
        response = self.inner.generate(
            system=system, prompt=prompt, seed=seed, max_tokens=max_tokens
        )
        self.usage.calls += 1
        self.usage.input_tokens += response.input_tokens
        self.usage.output_tokens += response.output_tokens
        self.usage.cost_usd += response.cost_usd
        self.usage.num_ctx = response.num_ctx
        return response


def load_oracle(task: TaskSpec) -> Oracle:
    """Same loader `bench/run_single.py` uses — imported from there so the
    suite and the by-hand dev tool can never disagree about what a task's
    oracle IS."""
    from bench.run_single import _load_oracle

    return _load_oracle(task)


def _record(
    *,
    run_id: str,
    task: TaskSpec,
    seed: int,
    state: AgentState,
    model_id: str,
    usage: Usage,
    latency_s: float,
    lib_versions: dict[str, str],
    sha: str,
) -> RunRecord:
    report = state.get("guarantee_report")
    static, semantic, resource = state.get("static"), state.get("semantic"), state.get("resource")

    def dump(result: BaseModel | None) -> dict | None:
        # `StaticResult.circuit_qpy` is raw QPY bytes. Pydantic's JSON mode
        # tries to decode them as UTF-8 and raises on the first non-text
        # byte, so persisting it unfiltered kills the run — which is exactly
        # what it did, on the first task whose code actually transpiled,
        # seven minutes into the 360-run suite.
        #
        # bench/run_single.py has excluded this field, with a comment saying
        # it is "never JSON-safe", since long before this line existed. The
        # knowledge was in the repository; it just wasn't applied where the
        # bytes were actually written to disk. Same shape as bug 11 (F11):
        # the fix went to the site that failed, not to the construction.
        #
        # There is nothing to keep, either: the circuit is reproducible from
        # `final_code`, and a results file is meant to be read.
        return result.model_dump(mode="json", exclude={"circuit_qpy"}) if result else None

    return RunRecord(
        run_id=run_id,
        task_id=task.task_id,
        model_id=model_id,
        seed=seed,
        status=cast(Any, state.get("status", "aborted")),
        iterations=state.get("iteration", 0),
        final_code=state.get("code", ""),
        static=dump(static),
        semantic=dump(semantic),
        resource=dump(resource),
        guarantee_report=report.model_dump(mode="json") if report is not None else None,
        error_history=[e.model_dump(mode="json") for e in state.get("error_history", [])],
        # Round-tripped through JSON with repr() as the fallback: the trace is
        # free-form per node, and one non-serializable value must not cost
        # the whole record the way circuit_qpy did (bug 14).
        trace=json.loads(json.dumps(state.get("trace", []), default=repr)),
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        num_ctx=usage.num_ctx,
        cost_usd=usage.cost_usd,
        latency_s=latency_s,
        git_sha=sha,
        lib_versions=lib_versions,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    )


TaskRunner = Callable[[TaskSpec, int, int], AgentState]


def _harness_error_state(task: TaskSpec, seed: int, during: str) -> AgentState:
    """The state a contained defect leaves behind. Built from the CURRENT
    exception, so it must only be called from inside an `except` block.

    `error_history` carries the full traceback because it is the only
    evidence the defect ever happened: after an unattended multi-hour run,
    a status with no traceback says something broke and nothing about what.
    """
    trace = traceback.format_exc()
    print(
        f"HARNESS ERROR in {task.task_id} seed={seed} while {during}:\n{trace}",
        file=sys.stderr,
        flush=True,
    )
    return cast(
        AgentState,
        {
            "status": "harness_error",
            "iteration": 0,
            "code": "",
            "error_history": [
                ErrorRecord(
                    iteration=0,
                    stage="harness",
                    error_type=type(sys.exc_info()[1]).__name__,
                    message=trace,
                )
            ],
        },
    )


def _run_one(runner: TaskRunner, task: TaskSpec, seed: int, max_iter: int) -> AgentState:
    """One run, with an unexpected exception CONTAINED to that run.

    The first live suite run died on its first task: a generated circuit
    ending in `measure_all()` raised inside the reference check, the
    exception left the graph, and 360 runs became zero results and a
    traceback. A regression suite that loses hours of work to one defect
    cannot be run often enough to be a regression suite (Principle III).

    The status is `harness_error`, NOT `infrastructure_error`. The two look
    similar and mean opposite things: an infrastructure error is the world
    failing us (a pool timeout, an unreachable provider) and is excluded
    from the metrics' denominator, so filing our OWN bugs there would hide
    them in the one bucket that nothing counts against us — the exact
    failure mode F10 describes. `harness_error` is loud by construction, and
    `analysis/metrics.py` refuses to call a run with any of them a clean
    baseline.

    `KeyboardInterrupt` and `SystemExit` are not caught: they aren't defects
    to record, they're a person asking the suite to stop.
    """
    try:
        return runner(task, seed, max_iter)
    except Exception:
        return _harness_error_state(task, seed, "running the graph")


def _fingerprint(state: AgentState) -> tuple[str, list[str], list[dict]]:
    messages = [
        e["message"] if isinstance(e, dict) else e.message for e in state.get("error_history", [])
    ]
    trace = json.loads(json.dumps(state.get("trace", []), default=repr))
    return state.get("code", ""), messages, trace


def verify_protocol(
    runner: TaskRunner,
    tasks: Iterable[TaskSpec],
    seeds: list[int],
    max_iter: int,
    reset_state: Callable[[], None] | None,
) -> list[str]:
    """Runs each canary task once per seed and returns one message per task
    whose seeds diverge, naming the first trace step where they part (F28:
    the trace is what located the original contamination in minutes)."""
    failures: list[str] = []
    for task in tasks:
        prints = {}
        for seed in seeds:
            if reset_state is not None:
                reset_state()
            prints[seed] = _fingerprint(_run_one(runner, task, seed, max_iter))
        base = seeds[0]
        for seed in seeds[1:]:
            if prints[seed] == prints[base]:
                continue
            a, b = prints[base][2], prints[seed][2]
            step = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None)
            where = f"trace step {step} ({a[step].get('node')})" if step is not None else "output"
            failures.append(f"{task.task_id}: seed {seed} differs from seed {base} at {where}")
    return failures


def run_suite(
    config: RunConfig,
    *,
    task_runner: TaskRunner | None = None,
    tasks_dir: Path = TASKS_DIR,
    usage: Usage | None = None,
    lib_versions: dict[str, str] | None = None,
    reset_state: Callable[[], None] | None = None,
    check_protocol: bool = False,
) -> Path:
    """Validates every configured reference, then runs the suite. Returns the
    JSONL path. `task_runner` and `lib_versions` are injectable so the
    Principle IV block can be tested without a sandbox, an LLM or a live
    Ollama (T100). `reset_state` is called before every run when
    `config.reset_per_run`; left None on the live path, it unloads the
    configured model. `check_protocol` runs the protocol canary first
    (`main()` always sets it) and raises ProtocolIntegrityError, running
    nothing, if its seeds diverge."""
    tasks = load_tasks(config, tasks_dir)
    failures = verify_references(tasks)
    if failures:
        raise UnverifiedReferenceError(
            f"{len(failures)} reference check(s) failed — refusing to run any of the "
            f"{len(tasks)} configured task(s) (Principle IV, FR-028):\n  " + "\n  ".join(failures)
        )

    sha = git_sha()
    run_id = make_run_id(config.model_dump(mode="json"), sha=sha)
    out_dir = config.results_dir / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "runs.jsonl"
    (out_dir / "config.yaml").write_text(yaml.safe_dump(config.model_dump(mode="json")))

    # Queries the configured Ollama server for its version (Principle III: the
    # record says which generator produced it), so it is a parameter — a run
    # with an injected task_runner has no such server to ask.
    if lib_versions is None:
        lib_versions = collect_lib_versions(ollama_base_url=config.ollama_url)
        # The retrieval corpus is part of what produced these numbers, so it
        # belongs in the record beside the library versions (Principle III).
        #
        # It is not a fixed quantity: `make index` SCRAPES the corpus live,
        # and a page that answers 503 is logged as SKIP and dropped while the
        # ingestion still exits 0. Two ingestions of the same code produced
        # 1020 and 1019 chunks for exactly that reason. Until the corpus is
        # pinned, a comparison between two runs is only meaningful if this
        # number matches — so it has to be visible in both.
        lib_versions = {
            **lib_versions,
            "qdocs_points": str(require_populated_index(QdrantClient(url=settings.qdrant_url))),
            "generator_provider": config.provider,
            "generator_host": config.generator_host,
        }
        if config.provider == "anthropic":
            from qcagent.llm.anthropic_client import EFFORT, THINKING_HEADROOM_TOKENS

            lib_versions |= {
                "anthropic_thinking": "adaptive",
                "anthropic_effort": EFFORT,
                "anthropic_thinking_headroom": str(THINKING_HEADROOM_TOKENS),
            }
        elif config.provider == "openrouter":
            from qcagent.llm import openrouter_client as orc

            lib_versions |= {
                "openrouter_reasoning_effort": config.reasoning_effort,
                "openrouter_reasoning_headroom": str(orc.REASONING_HEADROOM_TOKENS),
                "openrouter_pinned_provider": orc._PINNED_PROVIDER[config.model],
            }
        elif config.provider == "openai":
            from qcagent.llm import openrouter_client as orc

            lib_versions |= {
                "openai_reasoning_effort": config.reasoning_effort,
                "openai_temperature": "0" if config.send_temperature else "not sent",
                "openai_reasoning_headroom": str(orc.REASONING_HEADROOM_TOKENS),
            }
        elif config.provider == "groq":
            from qcagent.llm import openrouter_client as orc

            lib_versions |= {
                "groq_reasoning_effort": config.reasoning_effort,
                "groq_temperature": "0",
                "groq_reasoning_headroom": str(orc.REASONING_HEADROOM_TOKENS),
            }
        else:
            lib_versions |= {
                # Recorded because it CHANGES THE NUMBERS and is invisible
                # otherwise: a run at temperature 0 and one at the model default
                # are not comparable, and nothing in the results would say so
                # (F15).
                "ollama_temperature": str(settings.ollama_temperature),
                "ollama_num_ctx": str(settings.ollama_num_ctx),
                "generator_state": "reset_before_each_run"
                if config.reset_per_run
                else "reset_before_suite",
                # A guard whose result is not recorded is only half a guard.
                # Verified EXACTLY here and nowhere else: the check needs the
                # model loaded, `reset_generator_state` unloads it, and calling
                # it again later would re-warm the model and change the state the
                # run starts from — which is the protocol the 0/360 determinism
                # was measured under.
                "gpu_offload": f"{verify_gpu_offload(config.ollama_url, config.model):.0%}",
            }
    usage = usage or Usage()
    runner = task_runner or _graph_runner(config, usage)
    if reset_state is None and task_runner is None and config.provider == "ollama":

        def reset_state() -> None:
            reset_generator_state(config.ollama_url, config.model)

    if check_protocol and config.protocol_canary:
        canary = load_tasks(config.model_copy(update={"tasks": config.protocol_canary}), tasks_dir)
        canary_failures = verify_protocol(
            runner,
            canary,
            config.canary_seeds,
            config.max_iter,
            reset_state if config.reset_per_run else None,
        )
        if canary_failures:
            # Left in the run directory: the refusal is itself a result.
            (out_dir / "PROTOCOL_CHECK_FAILED.txt").write_text("\n".join(canary_failures) + "\n")
            raise ProtocolIntegrityError(
                "protocol canary: seeds diverge, so one seed is not a sample of anything "
                "(cross-task contamination is back, or the seed now matters at "
                "temperature 0 — F28, F29). Refusing to run:\n  " + "\n  ".join(canary_failures)
            )
        lib_versions = {
            **lib_versions,
            "protocol_canary": f"passed: {len(canary)} task(s) x {len(config.canary_seeds)} "
            "seeds byte-identical",
        }

    with jsonl.open("a") as sink:
        for task in tasks:
            for seed in config.seeds:
                if config.reset_per_run and reset_state is not None:
                    reset_state()
                usage.reset()
                started = time.perf_counter()
                state = _run_one(runner, task, seed, config.max_iter)
                # Building and serializing the record is INSIDE the guard
                # too. The first version of this containment wrapped only the
                # run itself, and the suite died anyway — in `_record`, on
                # non-UTF-8 QPY bytes, seven minutes in. Whatever survives
                # the graph still has to survive being written down, and
                # "the run succeeded but we couldn't save it" must cost one
                # record, not the remaining 353.
                try:
                    record = _record(
                        run_id=run_id,
                        task=task,
                        seed=seed,
                        state=state,
                        model_id=config.model,
                        usage=usage,
                        latency_s=time.perf_counter() - started,
                        lib_versions=lib_versions,
                        sha=sha,
                    )
                    line = record.model_dump_json()
                except Exception:
                    record = _record(
                        run_id=run_id,
                        task=task,
                        seed=seed,
                        state=_harness_error_state(task, seed, "recording the result"),
                        model_id=config.model,
                        usage=usage,
                        latency_s=time.perf_counter() - started,
                        lib_versions=lib_versions,
                        sha=sha,
                    )
                    line = record.model_dump_json()
                sink.write(line + "\n")
                sink.flush()  # append-only and durable per run, not per suite
                print(f"{task.task_id} seed={seed} -> {record.status}", flush=True)
    return jsonl


def _graph_runner(config: RunConfig, usage: Usage) -> TaskRunner:
    """The live path: real Ollama, real Qdrant-backed retrieval, real
    sandbox — the same graph `bench/run_single.py` drives by hand, with the
    LLM wrapped for accounting and one `WorkerPool` shared across the whole
    suite (D1b: the pool exists so process startup is paid once, not per
    task)."""
    inner: BaseLLMClient
    if config.provider == "anthropic":
        from qcagent.llm.anthropic_client import AnthropicClient

        if not settings.anthropic_api_key:
            raise RuntimeError("provider 'anthropic' needs ANTHROPIC_API_KEY in the environment")
        inner = AnthropicClient(settings.anthropic_api_key, config.model)
    elif config.provider == "openrouter":
        from qcagent.llm.openrouter_client import DEFAULT_BASE_URL, OpenRouterClient

        if not settings.fronteira_b_api_key:
            raise RuntimeError("provider 'openrouter' needs FRONTEIRA_B_API_KEY in the environment")
        inner = OpenRouterClient(
            settings.fronteira_b_api_key,
            config.model,
            settings.fronteira_b_base_url or DEFAULT_BASE_URL,
            effort=config.reasoning_effort,
        )
    elif config.provider == "openai":
        from qcagent.llm.openai_client import OpenAIClient

        if not settings.openai_api_key:
            raise RuntimeError("provider 'openai' needs OPENAI_API_KEY in the environment")
        inner = OpenAIClient(
            settings.openai_api_key,
            config.model,
            effort=config.reasoning_effort,
            send_temperature=config.send_temperature,
        )
    elif config.provider == "groq":
        from qcagent.llm.groq_client import DEFAULT_BASE_URL as GROQ_URL
        from qcagent.llm.groq_client import GroqClient

        if not settings.fronteira_b_api_key:
            raise RuntimeError("provider 'groq' needs FRONTEIRA_B_API_KEY in the environment")
        inner = GroqClient(
            settings.fronteira_b_api_key,
            config.model,
            settings.fronteira_b_base_url or GROQ_URL,
            effort=config.reasoning_effort,
        )
    else:
        inner = OllamaClient(
            config.ollama_url,
            config.model,
            settings.ollama_num_ctx,
            settings.ollama_temperature,
        )
        reset_generator_state(config.ollama_url, config.model)
    llm = AccountingLLM(inner, usage)
    qdrant = QdrantClient(url=settings.qdrant_url)
    embedder = FastEmbedEmbedder()
    pool = WorkerPool(size=settings.worker_pool_size, recycle_after=settings.worker_recycle_after)

    services = LiveServices(llm=llm, qdrant=qdrant, embedder=embedder, pool=pool)

    def run(task: TaskSpec, seed: int, max_iter: int) -> AgentState:
        graph = build_live_graph(
            services,
            seed=seed,
            max_iter=max_iter,
            oracle=load_oracle(task),
            distribution_tolerance=task.tolerance,
        )
        return cast(
            AgentState,
            graph.invoke(
                initial_state(
                    task_id=task.task_id,
                    spec=task.prompt,
                    oracle_ref=task.oracle_path,
                    coupling_map_name=task.coupling_map,
                    max_depth_ratio=task.max_depth_ratio,
                ),
                config={"recursion_limit": recursion_limit_for(max_iter)},
            ),
        )

    return run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="run the Principle IV reference check for the configured tasks and stop",
    )
    parser.add_argument(
        "--verify-protocol-only",
        action="store_true",
        help="run the protocol canary (F28/F29) against the live server and stop",
    )
    args = parser.parse_args(argv)

    config = RunConfig.load(args.config)
    tasks = load_tasks(config)
    failures = verify_references(tasks)
    if failures:
        print(
            f"REFUSING TO RUN: {len(failures)} reference check(s) failed across "
            f"{len(tasks)} configured task(s) (Principle IV, FR-028):",
            file=sys.stderr,
        )
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1
    print(f"{len(tasks)} task(s), {len(config.seeds)} seed(s): every reference verified")
    if args.verify_only:
        return 0
    if args.verify_protocol_only:
        usage = Usage()
        runner = _graph_runner(config, usage)
        canary = load_tasks(config.model_copy(update={"tasks": config.protocol_canary}))
        reset = None
        if config.reset_per_run and config.provider == "ollama":

            def reset() -> None:
                reset_generator_state(config.ollama_url, config.model)

        canary_failures = verify_protocol(
            runner, canary, config.canary_seeds, config.max_iter, reset
        )
        for failure in canary_failures:
            print(f"  DIVERGED {failure}", file=sys.stderr)
        verdict = "FAILED" if canary_failures else "passed"
        print(
            f"protocol canary {verdict}: {len(canary)} task(s) x {len(config.canary_seeds)} seeds"
        )
        return 1 if canary_failures else 0
    try:
        run_suite(config, check_protocol=True)
    except ProtocolIntegrityError as exc:
        print(f"REFUSING TO RUN: {exc}", file=sys.stderr)
        return 1
    return 0


def iter_records(jsonl: Path) -> Iterator[RunRecord]:
    """Reads a run's JSONL back. Used by analysis/metrics.py (T059)."""
    with jsonl.open() as handle:
        for line in handle:
            if line.strip():
                yield RunRecord.model_validate(json.loads(line))


if __name__ == "__main__":
    raise SystemExit(main())
