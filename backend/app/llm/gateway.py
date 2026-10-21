from enum import StrEnum

from app.core.config import settings
from app.llm.base import LLMClient, ToolCallingClient
from app.llm.gemini import GeminiLLMClient
from app.llm.hosted import AnthropicLLMClient
from app.llm.openrouter import OpenRouterLLMClient


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


def select_client(role: LLMRole = LLMRole.GENERATOR) -> LLMClient | None:
    """Kullanılacak LLM. Anahtar tanımlı değilse None: sistem LLM'siz modda çalışır.

    LLM_PROVIDER: "gemini" (varsayılan; doğrudan Gemini API), "openrouter" ya da "anthropic".
    Sonraki adım: kural tabanlı seçim (hassas / rutin → local, karmaşık → hosted).
    """
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
    if settings.llm_provider == "gemini":
        return GeminiLLMClient(
            api_key=settings.llm_api_key,
            model=model,
            purpose=role.value,
            thinking_level=thinking,
            timeout_s=settings.llm_timeout_s,
        )
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient(api_key=settings.llm_api_key, model=model)
    return OpenRouterLLMClient(
        api_key=settings.llm_api_key, model=model, base_url=settings.llm_base_url
    )


def select_orchestrator() -> ToolCallingClient | None:
    """Araç çağırabilen orkestratör; sağlayıcıda yoksa None (tutor doğrudan akışa düşer)."""
    client = select_client(LLMRole.ORCHESTRATOR)
    return client if isinstance(client, ToolCallingClient) else None


def select_judge_client() -> LLMClient:
    """Claim kontrolü için generator'dan farklı model ailesi."""
    raise NotImplementedError
