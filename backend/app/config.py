"""Application settings, read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo-root .env for local runs. Containers get real env vars and have no such file.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Each slice adds the settings it uses, so nothing needs a placeholder value."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str
    redis_url: str
    embedder_url: str
    seed_password: SecretStr | None = None  # dev only, read by scripts/seed.py


@lru_cache
def get_settings() -> Settings:
    """Return the settings, loaded once. Raises if a required variable is missing."""
    return Settings()
