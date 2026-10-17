from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://learning:learning@localhost:5432/learning_assistant"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    llm_provider: str = "local"
    llm_api_key: str = ""
    embedding_model: str = "intfloat/multilingual-e5-base"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
