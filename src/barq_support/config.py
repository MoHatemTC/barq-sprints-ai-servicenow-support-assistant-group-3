from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    qdrant_url: str
    qdrant_api_key: str
    chunk_size: int = 500
    chunk_overlap: int = 50

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()