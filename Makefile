.PHONY: up down migrate seed lint test

up:
	docker compose up -d --build --wait

down:
	docker compose down

migrate:
	cd backend && uv run --locked alembic upgrade head

seed:
	cd backend && PYTHONPATH=. uv run --locked python ../scripts/seed.py

# --locked fails if uv.lock is out of date with pyproject.toml.
lint:
	cd backend && uv run --locked ruff check --config pyproject.toml . ../scripts
	cd backend && uv run --locked ruff format --check --config pyproject.toml . ../scripts
	cd backend && uv run --locked mypy app

test:
	cd backend && uv run --locked pytest
