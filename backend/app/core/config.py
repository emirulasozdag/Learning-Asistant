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

    # Altyazısı olmayan ders videosu/sesi için yerel transkripsiyon (faster-whisper, ADR-6).
    # Model adı (ör. large-v3-turbo); boşsa kapalı: medya yüklemesi reddedilir, .vtt yüklenir.
    transcription_model: str = ""
    # Medya (video/ses) yükleme sınırı; VTT/PDF/PPTX için 50 MB sınırı ayrıdır.
    max_media_bytes: int = 2 * 1024 * 1024 * 1024

    # Alakasızlık kapısı (`retrieval/hybrid.py`): soru, en iyi anlamsal benzerlik ya da en iyi
    # parçanın anahtar kelime kapsaması (IDF ağırlıklı, 0–1) eşiğin üstündeyse dersle ilgili
    # sayılır; değilse "materyalde yok" denir ve LLM çağrılmaz. Eşikler kalibrasyon split'inde
    # ayarlanır (`python -m harness.retrieval_sweep`), held-out yalnızca raporlanır.
    retrieval_min_similarity: float = 0.78
    retrieval_min_keyword_coverage: float = 0.5
    # Takip sorusu tek başına kapıdan geçemezse önceki soruyla birlikte geçebilir, ama yalnızca
    # kendi benzerliği en az bu kadarsa (konu değiştiren alakasız soru içeri sızmasın).
    retrieval_follow_up_min_similarity: float = 0.77

    # Oturum (ADR-1): httpOnly çerez. Üretimde HTTPS arkasında SESSION_COOKIE_SECURE=true.
    session_cookie_name: str = "la_session"
    session_cookie_secure: bool = False
    session_ttl_hours: int = 24 * 7
    # Katılım kodunun geçerlilik süresi (gün); eğitmen yenileyince yeniden başlar (ADR-2).
    join_code_ttl_days: int = 120
    # Aydınlatma metninin güncel sürümü (ADR-4). Metin değişince artırılır; kullanıcı yeni
    # sürümü kabul edene kadar soru soramaz.
    privacy_policy_version: str = "2026-10-20"

    # Geliştirme hesapları (`python -m app.scripts.seed_demo`). Varsayılan kapalı; üretimde
    # açılmaz. Şifreler yalnızca .env'den gelir; boşsa hesap oluşturulmaz.
    seed_dev_accounts: bool = False
    dev_instructor_email: str = "egitmen@example.com"
    dev_instructor_password: str = ""
    dev_instructor_name: str = "Geliştirme Eğitmeni"
    dev_instructor_title: str = ""
    dev_student_email: str = "ogrenci@example.com"
    dev_student_password: str = ""
    dev_student_name: str = "Geliştirme Öğrencisi"
    # Sunum modu: giriş ekranı geliştirme hesaplarına (DEV_*_EMAIL) şifresiz giriş sunar ve
    # eğitmenin derslerinin katılım kodlarını gösterir. Yalnızca yerel demo içindir; üretimde
    # KAPALI kalır (ADR-1).
    demo_login: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


settings = Settings()
