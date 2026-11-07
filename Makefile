.PHONY: up down migrate seed embedder download synthetic parse-report ingest corpus-stats eval-check eval-retrieval hnsw-recall chunk-experiment lint test

up:
	docker compose up -d --build --wait

down:
	docker compose down

migrate:
	cd backend && uv run --locked alembic upgrade head

embedder:
	cd embedder && uv run --locked --extra ml uvicorn main:app --host 127.0.0.1 --port 8001

download:
	cd backend && PYTHONPATH=. uv run --locked python ../scripts/download.py --stage 1

synthetic:
	cd backend && uv run --locked python ../scripts/render_synthetic.py

parse-report:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/parse_report.py

ingest:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/ingest.py

eval-check:
	cd backend && PYTHONPATH=.:.. uv run --locked python -m eval.runner.retrieval --check $(SET)

CONFIG ?= all
eval-retrieval:
	cd backend && PYTHONPATH=.:.. uv run --locked python -m eval.runner.retrieval $(SET) $(CONFIG) $(LABEL) $(EVAL_FLAGS)

hnsw-recall:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/hnsw_recall.py ../eval/datasets/$(SET).jsonl

# ACTION=verify, ACTION=run VARIANT=<name>, or ACTION=report. Never writes to the main database.
chunk-experiment:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/chunk_experiment.py $(ACTION) $(VARIANT)

corpus-stats:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/corpus_stats.py

seed:
	cd backend && PYTHONPATH=. uv run --locked python ../scripts/seed.py

# --locked fails if uv.lock is out of date with pyproject.toml.
lint:
	cd backend && uv run --locked ruff check --config pyproject.toml . ../scripts ../eval
	cd backend && uv run --locked ruff format --check --config pyproject.toml . ../scripts ../eval
	cd backend && uv run --locked mypy app
	cd embedder && uv run --locked ruff check .
	cd embedder && uv run --locked ruff format --check .
	cd embedder && uv run --locked mypy main.py config.py

test:
	cd backend && uv run --locked pytest
	cd embedder && uv run --locked pytest
