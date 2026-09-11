import logging
logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI, HTTPException

from app.schemas import KBArticleListResponse
from app.servicenow_client import ServiceNowAuthError, ServiceNowClient, ServiceNowError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("main")

app = FastAPI(
    title="BARQ G3 - AI ServiceNow Support Assistant",
    description="Sprint 1 (S1.3): FastAPI Foundation & KB Retrieval Client",
    version="0.1.0",
)


@app.get("/", tags=["health"])
async def root() -> dict[str, str]:
    """فحص بسيط للتأكد إن السيرفر شغال."""
    return {"status": "ok", "service": "barq-g3-support-assistant"}


@app.get(
    "/kb-articles",
    response_model=KBArticleListResponse,
    tags=["knowledge-base"],
)
async def get_kb_articles() -> KBArticleListResponse:
    """
    يجيب كل مقالات الـ Knowledge Base المنشورة (published) من ServiceNow.

    ده الـ endpoint الرئيسي المطلوب في S1.3 - بيثبت إن الاتصال بـ
    ServiceNow Table API شغال، وإن المصادقة (Basic Auth) نجحت.
    """
    client = ServiceNowClient()

    try:
        articles = await client.get_published_kb_articles()
    except ServiceNowAuthError as exc:
        logger.error("Authentication error: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ServiceNowError as exc:
        logger.error("ServiceNow error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info("Returning %d KB article(s) to the client", len(articles))

    return KBArticleListResponse(count=len(articles), articles=articles)