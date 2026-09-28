"""
Celery application configuration with Redis 3.x compatibility patch.

The winget-installed Redis 3.0.504 doesn't support the RESP3 `HELLO` command.
We monkey-patch kombu's Channel._get_pool to inject `protocol=2` (RESP2) into
the connection pool parameters, preventing the HELLO handshake entirely.
"""
import logging

from celery import Celery
from kombu.transport import redis as kombu_redis
from redis.connection import ConnectionPool

from .settings import get_settings

logger = logging.getLogger(__name__)


def _patch_kombu_for_redis3() -> None:
    """
    Monkey-patch kombu's redis transport to inject `protocol=2` (RESP2) so
    that Celery workers can connect to Redis 3.x servers that don't support
    the RESP3 `HELLO` command.

    Safe to call multiple times — only patches once.
    """
    if getattr(kombu_redis.Channel, "_redis3_patched", False):
        return

    _original_get_pool = kombu_redis.Channel._get_pool

    def _patched_get_pool(self, asynchronous=False):
        params = self._connparams(asynchronous=asynchronous)
        params.setdefault("protocol", 2)  # RESP2: skip HELLO command
        self.keyprefix_fanout = self.keyprefix_fanout.format(db=params["db"])
        return ConnectionPool(**params)

    kombu_redis.Channel._get_pool = _patched_get_pool
    kombu_redis.Channel._redis3_patched = True
    logger.debug("kombu redis Channel._get_pool patched for Redis 3.x compatibility")


_patch_kombu_for_redis3()

settings = get_settings()

broker_url = settings.celery_broker_url or settings.redis_url
result_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery(
    "barq_support",
    broker=broker_url,
    backend=result_backend,
    include=["barq_support.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    broker_transport_options={
        "visibility_timeout": 3600,
    },
)
