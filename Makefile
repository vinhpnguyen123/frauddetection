.PHONY: up down migrate lint test

up:
	docker compose up -d --build --wait

down:
	docker compose down

migrate:
	cd backend && uv run --locked alembic upgrade head

# --locked fails if uv.lock is out of date with pyproject.toml.
lint:
	cd backend && uv run --locked ruff check .
	cd backend && uv run --locked ruff format --check .
	cd backend && uv run --locked mypy app

test:
	cd backend && uv run --locked pytest
