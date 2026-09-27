import logging

from fastapi import FastAPI

from .api.events import router as events_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("barq_support.main")

app = FastAPI(
    title="BARQ G3 - AI ServiceNow Support Assistant",
    description="Sprint 3 (S3.3): ServiceNow Webhook Ingestion & Dispatch Backend",
    version="0.3.3",
)

app.include_router(events_router)


@app.get("/", tags=["health"])
@app.get("/health", tags=["health"])
async def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "barq-g3-support-assistant",
        "version": "0.3.3",
    }
