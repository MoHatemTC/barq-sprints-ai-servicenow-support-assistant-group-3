"""FastAPI application factory.

Run with:  uv run uvicorn app.main:create_app --factory
(a factory keeps configuration loading out of import time, so tests and tooling can import
the package without a populated environment).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings
from app.container import Container, build_container
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


def create_app(container: Container | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owned: Container | None = None
        if app.state.container is None:
            settings = get_settings()  # fails fast with a clear message if env is invalid
            setup_logging(settings.log_level, settings.secret_values())
            owned = app.state.container = build_container(settings)
        logger.info("ServiceNow KB sync service started")
        try:
            yield
        finally:
            if owned is not None:
                owned.close()

    app = FastAPI(
        title="ServiceNow KB Sync",
        version="0.1.0",
        description="Keeps Qdrant in sync with ServiceNow knowledge articles.",
        lifespan=lifespan,
    )
    app.state.container = container
    app.include_router(router)
    return app
