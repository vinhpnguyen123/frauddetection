"""Embedder settings, read from the environment."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    embed_model: str
    embed_model_revision: str
    # The model's Python code lives in a separate repo, so it needs its own pin.
    embed_code_revision: str
    rerank_model: str
    rerank_model_revision: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
