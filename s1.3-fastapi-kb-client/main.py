
from fastapi import FastAPI, HTTPException, status
from servicenow_client import ServiceNowKBClient

app = FastAPI(title="AI ServiceNow Support Assistant")
kb_client = ServiceNowKBClient()

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "online"}

@app.get("/api/v1/kb-articles")
async def fetch_kb_articles(limit: int = 10):
    try:
        articles = await kb_client.get_published_kb_articles(limit=limit)
        return {
            "success": True,
            "count": len(articles),
            "data": articles
        }
    except Exception as e:
        raise HTTPException(
    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    detail=f"Failed to fetch KB articles: {type(e).__name__}: {str(e)!r}"
)