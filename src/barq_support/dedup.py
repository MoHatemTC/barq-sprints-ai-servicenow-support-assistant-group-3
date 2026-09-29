import logging
from typing import Any

import redis

from .settings import Settings, get_settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_redis_client(settings: Settings | None = None) -> redis.Redis:
    """Get or create singleton Redis client instance."""
    global _redis_client
    if _redis_client is None:
        if settings is None:
            settings = get_settings()
        _redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            protocol=2,  # Redis 3.x compat: skip HELLO handshake
        )
    return _redis_client


def extract_event_id(payload: dict[str, Any]) -> str | None:
    """
    Extract the event's unique identifier from the webhook payload.
    Supports incident_sys_id (standard ServiceNow Business Rule payload),
    sys_id, or event_id.
    """
    candidate = (
        payload.get("event_id")
        or payload.get("incident_sys_id")
        or payload.get("sys_id")
        or payload.get("article_id")   # KB article webhook events
    )
    if candidate is not None:
        cand_str = str(candidate).strip()
        if cand_str:
            return cand_str
    return None


def check_and_set_dedup(
    event_id: str,
    redis_client: redis.Redis | None = None,
    ttl_seconds: int = 86400,
) -> bool:
    """
    Atomically SETNX a key `evt:<event_id>` with TTL (default ~24h / 86400s).

    Returns:
        True if the key was newly set (proceed to dispatch).
        False if the key already exists (replay detected, skip dispatch).
    """
    if redis_client is None:
        redis_client = get_redis_client()

    key = f"evt:{event_id}"
    is_new = bool(redis_client.set(key, "1", nx=True, ex=ttl_seconds))

    if not is_new:
        logger.info("Replay detected for key %s (already in Redis)", key)
    else:
        logger.info(
            "Dedup gate passed: recorded new event key %s with TTL %ds",
            key,
            ttl_seconds,
        )

    return is_new
