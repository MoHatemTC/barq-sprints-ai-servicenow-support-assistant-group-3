"""Environment-driven configuration with validation. No defaults for secrets or URLs."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_TOKEN = re.compile(r"^[A-Za-z0-9_\-]+$")


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- ServiceNow ---------------------------------------------------------
    service_now_url: str = Field(min_length=1)
    service_now_username: str = Field(min_length=1)
    service_now_password: SecretStr
    service_now_table: str = "kb_knowledge"
    # Comma separated; compared case-insensitively against workflow_state.
    service_now_published_states: str = "published"
    # Comma separated kb_knowledge_base sys_ids. Empty = every knowledge base.
    service_now_kb_sys_ids: str = ""
    service_now_page_size: int = Field(default=100, ge=1, le=1000)
    service_now_timeout_seconds: float = Field(default=30.0, gt=0)
    service_now_max_retries: int = Field(default=3, ge=0, le=10)

    # --- Qdrant -------------------------------------------------------------
    qdrant_url: str = Field(min_length=1)
    qdrant_api_key: SecretStr | None = None
    qdrant_collection: str = Field(min_length=1)
    qdrant_text_field: str = "text"
    qdrant_vector_name: str | None = None
    qdrant_distance: Literal["Cosine", "Dot", "Euclid"] = "Cosine"

    # --- Embeddings ---------------------------------------------------------
    embedding_api_key: SecretStr
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_batch_size: int = Field(default=64, ge=1, le=2048)
    embedding_include_title: bool = True

    # --- Chunking (characters) ---------------------------------------------
    chunk_size: int = Field(default=500, gt=0)
    chunk_overlap: int = Field(default=50, ge=0)

    # --- API security (optional) -------------------------------------------
    api_auth_token: SecretStr | None = None
    webhook_secret: SecretStr | None = None

    # --- Sync behaviour -----------------------------------------------------
    sync_state_path: str = ".state/last_sync.json"
    sync_initial_lookback_hours: int = Field(default=24, ge=1)

    log_level: str = "INFO"

    # ------------------------------------------------------------------ validators
    @field_validator(
        "qdrant_api_key", "qdrant_vector_name", "api_auth_token", "webhook_secret", mode="before"
    )
    @classmethod
    def _empty_to_none(cls, value):
        """`KEY=` in a .env file yields an empty string; treat it as unset."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("service_now_password", "embedding_api_key")
    @classmethod
    def _secret_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("service_now_url", "qdrant_url", "embedding_base_url")
    @classmethod
    def _normalize_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not re.match(r"^https?://\S+$", value):
            raise ValueError("must be an http(s) URL")
        return value

    @field_validator("service_now_published_states", "service_now_kb_sys_ids")
    @classmethod
    def _safe_csv(cls, value: str) -> str:
        # These values are interpolated into a ServiceNow encoded query, where '^' is an operator.
        for item in _split_csv(value):
            if not _SAFE_TOKEN.match(item):
                raise ValueError(
                    f"invalid value {item!r}: only letters, digits, '_' and '-' allowed"
                )
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_level(cls, value: str) -> str:
        value = value.upper()
        if value not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("must be a standard logging level")
        return value

    @model_validator(mode="after")
    def _check_chunking(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        if not _split_csv(self.service_now_published_states):
            raise ValueError("SERVICE_NOW_PUBLISHED_STATES must list at least one state")
        return self

    # ------------------------------------------------------------------ helpers
    @property
    def published_states(self) -> list[str]:
        return [s.lower() for s in _split_csv(self.service_now_published_states)]

    @property
    def kb_sys_ids(self) -> list[str]:
        return _split_csv(self.service_now_kb_sys_ids)

    def secret_values(self) -> list[str]:
        """All secret strings, used to redact logs."""
        secrets = [
            self.service_now_password,
            self.embedding_api_key,
            self.qdrant_api_key,
            self.api_auth_token,
            self.webhook_secret,
        ]
        return [s.get_secret_value() for s in secrets if s is not None]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
