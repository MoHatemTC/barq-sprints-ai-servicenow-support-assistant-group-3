from typing import Optional
from pydantic import BaseModel, Field


class KBArticle(BaseModel):
    """
    Data shape for a single article record from the kb_knowledge table in ServiceNow.
    """

    sys_id: str = Field(..., description="Unique identifier for the record in ServiceNow")
    number: str = Field(..., description="Article number, e.g. KB0001")
    short_description: str = Field(default="", description="Short title of the article")
    text: Optional[str] = Field(default=None, description="Full article content (HTML)")
    workflow_state: Optional[str] = Field(
        default=None, description="Publication state: draft, review, published, retired..."
    )
    category: Optional[str] = Field(default=None, description="Article category")
    kb_knowledge_base: Optional[str] = Field(
        default=None, description="sys_id of the Knowledge Base this article belongs to"
    )
    sys_created_on: Optional[str] = Field(default=None, description="Record creation date")
    sys_updated_on: Optional[str] = Field(default=None, description="Last update date of the record")

    class Config:
        extra = "ignore"


class KBArticleListResponse(BaseModel):
    """Response shape returned by our endpoint for the list of articles."""

    count: int = Field(..., description="Number of articles returned")
    articles: list[KBArticle] = Field(default_factory=list)