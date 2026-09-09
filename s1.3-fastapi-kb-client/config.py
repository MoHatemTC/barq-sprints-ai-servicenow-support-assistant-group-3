from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    servicenow_instance_url: str
    servicenow_client_id: str
    servicenow_client_secret: str
    servicenow_username: str
    servicenow_password: str
    fastapi_port: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()