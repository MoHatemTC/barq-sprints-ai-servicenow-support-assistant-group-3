from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    llm_api_key: str = Field(default="")
    llm_model: str = Field(default="")
    llm_base_url: str = Field(default="")

    # Password classifier (vLLM)
    password_classifier_base_url: str = Field(default="")
    password_classifier_api_key: str = Field(default="")
    password_classifier_model: str = Field(
        default="Qwen/Qwen2.5-1.5B-Instruct"
    )
    password_classifier_timeout_seconds: float = Field(default=10.0, gt=0)

    # ServiceNow
    servicenow_instance_url: str = Field(default="")
    servicenow_username: str = Field(default="")
    servicenow_password: str = Field(default="")

    # Qdrant
    qdrant_url: str = Field(default="")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="kb_articles")
    
    #langfuse
    langfuse_public_key: str = Field(default="")
    langfuse_secret_key: str = Field(default="")
    langfuse_host: str = Field(default="https://cloud.langfuse.com")

    # Agent
    agent_max_iterations: int = Field(default=5)

    # KB ingestion
    chunk_size: int = Field(default=500)
    chunk_overlap: int = Field(default=50)
    

    # Webhook & Dedup
    servicenow_webhook_secret: str = Field(default="")
    webhook_dedup_ttl_seconds: int = Field(default=86400)

    # Redis & Celery
    redis_url: str = Field(default="redis://localhost:6379/0")
    celery_broker_url: str = Field(default="")
    celery_result_backend: str = Field(default="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
