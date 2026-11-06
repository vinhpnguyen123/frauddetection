.PHONY: lint test

# --locked fails if uv.lock is out of date with pyproject.toml.
lint:
	cd backend && uv run --locked ruff check .
	cd backend && uv run --locked ruff format --check .
	cd backend && uv run --locked mypy app

test:
	cd backend && uv run --locked pytest
