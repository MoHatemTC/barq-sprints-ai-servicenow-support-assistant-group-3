"""Logging setup with secret redaction (passwords, API keys, tokens never reach the logs)."""

from __future__ import annotations

import logging
from collections.abc import Iterable


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        # Ignore very short values: they would corrupt unrelated log text.
        self._secrets = [s for s in secrets if s and len(s) >= 4]

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)  # includes traceback text
        for secret in self._secrets:
            text = text.replace(secret, "***")
        return text


def setup_logging(level: str = "INFO", secrets: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter("%(asctime)s %(levelname)s [%(name)s] %(message)s", secrets)
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Libraries log full request URLs at INFO; keep them quiet.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
