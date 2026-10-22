.PHONY: install models index eval verify-suite eval-retrieval validate-oracles run report test lint typecheck smoke

install:
	uv sync --group dev
	uv run pre-commit install

# research.md D18b — the ONLY step that downloads model weights: the pinned
# revisions in src/qcagent/retrieval/embedding.py, into .cache/fastembed (or
# FASTEMBED_CACHE_PATH). Run once per machine outside the image; everything
# else, including `make test`, loads them offline and never reaches the network.
models:
	uv run python scripts/fetch_models.py

index:
	uv run python -m qcagent.retrieval.ingest

# US6 — the interface. Same graph as the suite (qcagent.live.build_live_graph),
# read-only with respect to results/. Reachable at http://localhost:8000 once
# docker-compose publishes the port; in the sandboxed dev environment the host
# additionally needs `sbx ports <sandbox> --publish 8000:8000/tcp`.
ui:
	uv run uvicorn qcagent.ui.app:app --host 0.0.0.0 --port 8000

eval:
	uv run python -m bench.runner --config config.yaml

# M1 gate — recall@8/MRR over tests/retrieval/queries.jsonl, per query_type
# (T041). Requires a populated Qdrant (`make index` first).
eval-retrieval:
	uv run python -m analysis.eval_retrieval --verbose

# Blocking dataset gate (T050, FR-018) — independent-construction + property
# checks for every oracle in bench/tasks/. Must pass before any oracle ships.
validate-oracles:
	uv run python -m bench.validate_oracles

# Dev inspection tool — one TaskSpec through the US1 graph, by hand:
#   make run TASK=bench/tasks/t1_primitives/ghz_3q.json
run:
	uv run python -m bench.run_single $(TASK) --profile $(or $(PROFILE),local-7b)

# Principle IV, without running anything: re-validates every reference named
# in config.yaml and stops. The same check runs automatically before `eval`.
verify-suite:
	uv run python -m bench.runner --config config.yaml --verify-only

# Metrics for the most recent run (or pass a path). `analysis.ablation` is
# gone with v2's experimental matrix (MIGRATION.md); comparing two runs is
# `analysis.compare BEFORE AFTER`.
report:
	uv run python -m analysis.metrics

test:
	uv run pytest

smoke:
	uv run pytest -m smoke

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src/qcagent
