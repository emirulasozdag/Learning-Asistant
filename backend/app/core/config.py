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
    # gemini (doğrudan Gemini API) | openrouter | anthropic. Seçim: DECISIONS.md ADR-7.
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    # Öğretim içeriğini üreten model (cevap, açıklama; sonra pratik ve değerlendirme).
    # Boşsa sağlayıcının varsayılanı (`generator_model`). OpenRouter'da "anthropic/claude-…" gibi.
    llm_model: str = ""
    # Konuşmayı yöneten orkestratör: araç seçer, öğretim içeriği yazmaz; hızlı ve ucuz model yeter.
    # Boşsa sağlayıcının varsayılanı. Araç çağırma şimdilik yalnızca gemini sağlayıcısında var.
    llm_orchestrator_model: str = ""
    # Gemini düşünme seviyesi: minimal | low | medium | high. Model desteklemiyorsa en yakın
    # desteklenen seviye kullanılır (`llm/catalog.py`). Düşünme token'ları çıktı olarak ücretlenir.
    llm_thinking_level: str = "low"
    llm_orchestrator_thinking_level: str = "minimal"
    # Bağımsız kontrolcü (pratik sorusunu anahtarı görmeden çözer). Boşsa üretici modeli; ayrı
    # çağrı ve bağlamla çalışır. Judge (iddia kontrolü, #10) bundan ayrıdır: farklı model ailesi.
    llm_checker_model: str = ""
    llm_checker_thinking_level: str = "low"
    llm_timeout_s: float = 90.0
    # OpenAI uyumlu uç nokta (openrouter sağlayıcısı için). Yerel model: http://localhost:11434/v1
    llm_base_url: str = "https://openrouter.ai/api/v1"

    # AI Tutor (orkestratör, `app/tutor/`). Bir turda en fazla bu kadar araç adımı.
    tutor_max_steps: int = 4
    # Kaynaklı cevapta yeniden sıralama (`retrieval/rerank.py`): aramanın bu kadar adayı hızlı
    # modelle puanlanır, en iyi `keep` parça üreticiye gider. 0 = kapalı (aramanın ilk 5'i).
    tutor_rerank_candidates: int = 20
    tutor_rerank_keep: int = 6
    # Materyalde olmayan ama ders alanı içindeki sorulara "genel bilgi" etiketli açıklama
    # (ADR-7, köken politikası). Eğitmen/ekip kararı verilene kadar kapalı.
    tutor_general_knowledge: bool = False

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

    @property
    def generator_model(self) -> str:
        return self.llm_model or _DEFAULT_MODELS.get(self.llm_provider, ("", ""))[0]

    @property
    def orchestrator_model(self) -> str:
        return self.llm_orchestrator_model or _DEFAULT_MODELS.get(self.llm_provider, ("", ""))[1]

    @property
    def llm_endpoint(self) -> str:
        """Kayıtlarda (eval run) gösterilen, isteklerin gittiği uç nokta."""
        if self.llm_provider == "gemini":
            return "https://generativelanguage.googleapis.com"
        if self.llm_provider == "anthropic":
            return "https://api.anthropic.com"
        return self.llm_base_url


# Sağlayıcı başına (üretici, orkestratör) varsayılan modeller. Gerekçe ve fiyatlar: ADR-7,
# `llm/catalog.py`. Orkestratör boşsa o sağlayıcıda araç çağırma yok: tutor doğrudan akışa düşer.
_DEFAULT_MODELS = {
    "gemini": ("gemini-3.8-flash", "gemini-3.5-flash-lite"),
    "openrouter": ("anthropic/claude-opus-5.5", ""),
    "anthropic": ("claude-opus-5-5", ""),
}


settings = Settings()
