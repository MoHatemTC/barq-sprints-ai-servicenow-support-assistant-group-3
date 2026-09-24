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
    gemini_api_key: str = Field(default="")

    # ServiceNow
    servicenow_instance_url: str = Field(default="")
    servicenow_username: str = Field(default="")
    servicenow_password: str = Field(default="")

    # Qdrant
    qdrant_url: str = Field(default="")
    qdrant_api_key: str = Field(default="")
    qdrant_collection: str = Field(default="kb_articles")

    # Agent
    agent_max_iterations: int = Field(default=5)


@lru_cache
def get_settings() -> Settings:
    return Settings()