.PHONY: up down migrate seed embedder download synthetic parse-report ingest corpus-stats hnsw-recall lint test

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

hnsw-recall:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/hnsw_recall.py ../eval/datasets/$(SET).jsonl

corpus-stats:
	cd backend && PYTHONPATH=.:.. uv run --locked python ../scripts/corpus_stats.py

seed:
	cd backend && PYTHONPATH=. uv run --locked python ../scripts/seed.py

# --locked fails if uv.lock is out of date with pyproject.toml.
lint:
	cd backend && uv run --locked ruff check --config pyproject.toml . ../scripts
	cd backend && uv run --locked ruff format --check --config pyproject.toml . ../scripts
	cd backend && uv run --locked mypy app
	cd embedder && uv run --locked ruff check .
	cd embedder && uv run --locked ruff format --check .
	cd embedder && uv run --locked mypy main.py config.py

test:
	cd backend && uv run --locked pytest
	cd embedder && uv run --locked pytest
