.PHONY: install index eval eval-retrieval run report test lint typecheck smoke

install:
	uv sync --group dev
	uv run pre-commit install

index:
	uv run python -m qcagent.retrieval.ingest

eval:
	uv run python -m bench.runner --config config.yaml

# M1 gate — recall@8/MRR over tests/retrieval/queries.jsonl, per query_type
# (T041). Requires a populated Qdrant (`make index` first).
eval-retrieval:
	uv run python -m analysis.eval_retrieval --verbose

# Dev inspection tool — one TaskSpec through the US1 graph, by hand:
#   make run TASK=bench/tasks/t1_primitives/ghz_3q.json
run:
	uv run python -m bench.run_single $(TASK)

report:
	uv run python -m analysis.metrics
	uv run python -m analysis.ablation

test:
	uv run pytest

smoke:
	uv run pytest -m smoke

lint:
	uv run ruff check .
	uv run ruff format --check .

typecheck:
	uv run mypy src/qcagent
