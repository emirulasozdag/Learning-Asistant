from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    # backend/ içinden çalışınca kökteki .env de okunur.
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://learning:learning@localhost:5432/learning_assistant"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # Yüklenen orijinal dosyalar (git'e girmez).
    upload_dir: Path = Path("data/uploads")
    # Üretilen sayfa görüntüleri (silinebilir; gerektiğinde yeniden oluşturulur).
    cache_dir: Path = Path("data/cache")
    # Frontend API'ye bu önekle ulaşır (Vite proxy); dosya linkleri buna göre üretilir.
    public_api_prefix: str = "/api"

    # LLM: anahtar boşsa sistem LLM'siz çalışır (en ilgili parçayı alıntılar).
    # openrouter | anthropic
    llm_provider: str = "openrouter"
    llm_api_key: str = ""
    # OpenRouter model kimliği (ör. anthropic/claude-opus-5.5, anthropic/claude-haiku-5.5).
    llm_model: str = "anthropic/claude-opus-5.5"
    # OpenAI uyumlu uç nokta (openrouter sağlayıcısı için). Yerel model: http://localhost:11434/v1
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # e5 (yerel model) | fake (testler; model indirmez)
    embedding_provider: str = "e5"
    embedding_model: str = "intfloat/multilingual-e5-base"

    # Hiç kelime eşleşmesi yokken, en iyi anlamsal benzerlik bunun altındaysa soru
    # "materyalde yok" sayılır ve LLM çağrılmaz. e5 ile ölçüm: ders soruları 0.81–0.88,
    # alakasız sorular 0.72–0.76; dersle ilgili ama materyalde olmayanlara LLM karar verir.
    retrieval_min_similarity: float = 0.78

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
