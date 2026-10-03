"""Tiny JSON file that remembers the last successful sync time."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class SyncStateStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> datetime | None:
        try:
            data = json.loads(self.path.read_text())
            parsed = datetime.fromisoformat(data["last_sync"])
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, OSError) as exc:
            logger.warning("Ignoring unreadable sync state file %s: %s", self.path, exc)
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed

    def save(self, when: datetime) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"last_sync": when.astimezone(UTC).isoformat()}, handle)
            os.replace(tmp, self.path)  # atomic
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
