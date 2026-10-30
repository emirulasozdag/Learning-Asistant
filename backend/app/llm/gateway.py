import logging
from enum import StrEnum

from app.core.config import settings
from app.llm.base import LLMClient, ToolCallingClient
from app.llm.gemini import GeminiLLMClient
from app.llm.hosted import AnthropicLLMClient
from app.llm.local import LocalLLMClient
from app.llm.openrouter import OpenRouterLLMClient
from app.llm.routing import DataClass, route_for

logger = logging.getLogger(__name__)


class LLMRole(StrEnum):
    """Modelin sistemdeki görevi; her görev kendi modeli ve düşünme seviyesiyle çalışır."""

    # Öğretim içeriği üretir: kaynaklı cevap, genel açıklama; sonra pratik ve değerlendirme.
    GENERATOR = "generator"
    # Konuşmayı yönetir, araç seçer; öğrenciye giden içeriği yazmaz (ADR-7).
    ORCHESTRATOR = "orchestrator"
    # Üretileni bağımsız kontrol eder (pratik sorusunu anahtarı görmeden çözer); ayrı çağrı.
    CHECKER = "checker"
    # Arama adaylarını soruya katkısına göre puanlar; orkestratörle aynı hızlı model.
    RERANKER = "reranker"


def select_client(
    role: LLMRole = LLMRole.GENERATOR, data: DataClass = DataClass.COURSE_EVIDENCE
) -> LLMClient | None:
    """Kullanılacak LLM. Anahtar tanımlı değilse None: sistem LLM'siz modda çalışır.

    LLM_PROVIDER: "gemini" (varsayılan; doğrudan Gemini API), "openrouter" ya da "anthropic".
    `data`: yükün en hassas parçası (ADR-8). Yerele yönlenen veri için yerel istemci döner;
    yerel model yapılandırılmamışsa bu istemci açık bir hatayla durur, hosted'a düşmez.
    """
    if route_for(data) == "local":
        return LocalLLMClient(settings.llm_local_base_url, settings.llm_local_model)
    if not settings.llm_api_key:
        return None
    model, thinking = {
        LLMRole.GENERATOR: (settings.generator_model, settings.llm_thinking_level),
        LLMRole.ORCHESTRATOR: (
            settings.orchestrator_model,
            settings.llm_orchestrator_thinking_level,
        ),
        LLMRole.CHECKER: (
            settings.llm_checker_model or settings.generator_model,
            settings.llm_checker_thinking_level,
        ),
        LLMRole.RERANKER: (
            settings.orchestrator_model,
            settings.llm_orchestrator_thinking_level,
        ),
    }[role]
    if not model:
        return None
    return _build_client(
        settings.llm_provider,
        api_key=settings.llm_api_key,
        model=model,
        base_url=settings.llm_base_url,
        purpose=role.value,
        thinking=thinking,
    )


def select_orchestrator() -> ToolCallingClient | None:
    """Araç çağırabilen orkestratör; sağlayıcıda yoksa None (tutor doğrudan akışa düşer)."""
    client = select_client(LLMRole.ORCHESTRATOR)
    return client if isinstance(client, ToolCallingClient) else None


class JudgeConfigError(ValueError):
    """Judge ayarı geçersiz: bilinmeyen sağlayıcı ya da generator'la aynı model ailesi."""


JUDGE_PROVIDERS = ("gemini", "openrouter", "anthropic", "local")

# Model adının başına göre aile (OpenRouter'da "sağlayıcı/model" biçimi de olur).
_FAMILIES = (
    ("gemini", ("gemini", "gemma")),
    ("claude", ("claude",)),
    ("gpt", ("gpt", "o1", "o3", "o4", "chatgpt")),
    ("llama", ("llama", "meta-llama")),
    ("qwen", ("qwen",)),
    ("mistral", ("mistral", "mixtral", "codestral", "magistral")),
    ("deepseek", ("deepseek",)),
)


def model_family(provider: str, model: str) -> str:
    """Modelin ailesi (judge'ın generator'dan farklı olduğunu denetlemek için, ANALYSIS §7.3)."""
    if provider == "gemini":
        return "gemini"
    if provider == "anthropic":
        return "claude"
    vendor, _, name = model.lower().rpartition("/")
    for family, prefixes in _FAMILIES:
        if name.startswith(prefixes) or vendor.startswith(prefixes):
            return family
    return vendor or name


def select_judge_client() -> LLMClient | None:
    """İddia kontrolü (#10) için judge. Yapılandırılmamışsa None.

    Judge generator'dan farklı model ailesinden olmalı; aynı aileyse `JudgeConfigError`
    (self-preference yanlılığı, ANALYSIS §7.3). Judge'a giden yük soru, cevap ve onaylı ders
    parçalarıdır (DataClass.COURSE_EVIDENCE); kimlik gitmez.
    """
    provider, model = settings.judge_provider, settings.judge_model
    if not provider or not model:
        return None
    if provider not in JUDGE_PROVIDERS:
        raise JudgeConfigError(
            f"JUDGE_PROVIDER '{provider}' geçersiz; {', '.join(JUDGE_PROVIDERS)} olmalı."
        )
    judge_family = model_family(provider, model)
    generator_family = model_family(settings.llm_provider, settings.generator_model)
    if judge_family == generator_family:
        raise JudgeConfigError(
            f"Judge ({provider}/{model}) generator ile aynı model ailesinden ({judge_family}); "
            "farklı bir aile seçin (JUDGE_PROVIDER, JUDGE_MODEL)."
        )
    if provider == "local":
        return LocalLLMClient(settings.llm_local_base_url, model)
    api_key = settings.judge_api_key or (
        settings.llm_api_key if provider == settings.llm_provider else ""
    )
    if not api_key:
        raise JudgeConfigError("Judge için API anahtarı yok (JUDGE_API_KEY).")
    return _build_client(
        provider,
        api_key=api_key,
        model=model,
        base_url=settings.judge_base_url,
        purpose="judge",
        thinking=settings.llm_checker_thinking_level,
    )


def resolve_judge() -> tuple[LLMClient | None, str | None]:
    """(judge, yapılandırma hatası). Hata fırlatmaz: hatalı ayar kontrolün başarısız sayılmasıyla
    sonuçlanır ve öğrenciye kontrol edilmemiş metin gitmez."""
    try:
        return select_judge_client(), None
    except JudgeConfigError as exc:
        logger.error("Judge yapılandırması geçersiz: %s", exc)
        return None, str(exc)


def _build_client(
    provider: str, *, api_key: str, model: str, base_url: str, purpose: str, thinking: str
) -> LLMClient:
    if provider == "gemini":
        return GeminiLLMClient(
            api_key=api_key,
            model=model,
            purpose=purpose,
            thinking_level=thinking,
            timeout_s=settings.llm_timeout_s,
        )
    if provider == "anthropic":
        return AnthropicLLMClient(api_key=api_key, model=model)
    # Diğer her değer OpenAI uyumlu uç nokta (openrouter); generator için önceki davranış.
    return OpenRouterLLMClient(api_key=api_key, model=model, base_url=base_url)
