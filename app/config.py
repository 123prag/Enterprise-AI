"""Central application configuration.

Every environment-dependent choice in the system (LLM provider, embedding
provider, database backend, vector store backend) is driven from here so the
same codebase runs in two modes:

- ``APP_ENV=local``      -> SQLite + FAISS + a deterministic offline "dummy"
  LLM/embedder. No network access and no API keys required. This is what
  CI and this sandbox run.
- ``APP_ENV=production`` -> PostgreSQL + Qdrant + a real LLM provider
  (OpenAI/Anthropic), configured purely via environment variables.

No other module should read ``os.environ`` directly — everything funnels
through ``Settings`` so the swap points are explicit and testable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime mode ---
    app_env: Literal["local", "production"] = "local"

    # --- LLM ---
    llm_provider: Literal["dummy", "openai", "anthropic"] = "dummy"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_max_tokens: int = 1000
    llm_temperature: float = 0.1

    # --- Embeddings ---
    embedding_provider: Literal["dummy", "openai", "sentence-transformers"] = "dummy"
    embedding_model: str = "text-embedding-3-small"
    embedding_api_key: str = ""

    # --- Database ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'local.db'}"

    # --- Vector store ---
    vector_store_provider: Literal["faiss", "qdrant"] = "faiss"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    faiss_index_dir: str = str(PROJECT_ROOT / "data" / "vector_store")

    # --- API ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_rate_limit_per_minute: int = 60
    api_auth_token: str = ""

    # --- Observability ---
    otel_enabled: bool = False
    otel_exporter_endpoint: str = ""
    log_level: str = "INFO"

    # --- Guardrails ---
    max_agent_retries: int = 2
    diagnosis_confidence_threshold: float = 0.7
    human_review_risk_threshold: Literal["low", "medium", "high"] = "medium"

    @property
    def is_local(self) -> bool:
        return self.app_env == "local"


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()
