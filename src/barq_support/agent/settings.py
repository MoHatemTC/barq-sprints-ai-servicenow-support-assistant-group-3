"""Runtime configuration.

Every credential / endpoint setting comes from environment variables (optionally
populated from a local, git-ignored ``.env`` file). Nothing is hardcoded and the
API key is never printed or logged (``repr=False``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigError(RuntimeError):
    """Raised when required environment configuration is missing or invalid."""


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number (got {raw!r}).") from exc


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer (got {raw!r}).") from exc


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)  # repr=False: never leak the key via logs/tracebacks
    model: str
    base_url: str | None = None
    temperature: float | None = 0.0
    timeout_seconds: float = 60.0
    max_retries: int = 2
    agent_max_iterations: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from the process environment (loading ``.env`` if present)."""
        try:
            from dotenv import load_dotenv

            load_dotenv(override=False)  # real environment variables always win
        except ImportError:  # python-dotenv is optional at runtime
            pass

        missing = [n for n in ("LLM_API_KEY", "LLM_MODEL") if not os.getenv(n, "").strip()]
        if missing:
            raise ConfigError(
                "Missing required environment variable(s): "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill it in."
            )

        temp_raw = os.getenv("LLM_TEMPERATURE", "0").strip().lower()
        temperature = None if temp_raw in ("none", "null") else _float_env("LLM_TEMPERATURE", 0.0)

        return cls(
            api_key=os.environ["LLM_API_KEY"].strip(),
            model=os.environ["LLM_MODEL"].strip(),
            base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
            temperature=temperature,
            timeout_seconds=_float_env("LLM_TIMEOUT_SECONDS", 60.0),
            max_retries=_int_env("LLM_MAX_RETRIES", 2),
            agent_max_iterations=_int_env("AGENT_MAX_ITERATIONS", 5),
        )
