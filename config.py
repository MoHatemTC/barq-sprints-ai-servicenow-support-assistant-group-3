from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    qdrant_url: str
    qdrant_api_key: str
    chunk_size: int = 500
    chunk_overlap: int = 50
    hf_token: str | None = None

    class Config:
        env_file = ".env"

settings = Settings()