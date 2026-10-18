from app.core.config import settings
from app.llm.base import LLMClient
from app.llm.hosted import AnthropicLLMClient
from app.llm.openrouter import OpenRouterLLMClient


def select_client() -> LLMClient | None:
    """Kullanılacak LLM. Anahtar tanımlı değilse None: sistem LLM'siz modda çalışır.

    LLM_PROVIDER: "openrouter" (varsayılan; her modele tek anahtarla) ya da "anthropic".
    Sonraki adım: kural tabanlı seçim (hassas / rutin → local, karmaşık → hosted).
    """
    if not settings.llm_api_key:
        return None
    if settings.llm_provider == "anthropic":
        return AnthropicLLMClient(api_key=settings.llm_api_key, model=settings.llm_model)
    return OpenRouterLLMClient(
        api_key=settings.llm_api_key, model=settings.llm_model, base_url=settings.llm_base_url
    )


def select_judge_client() -> LLMClient:
    """Claim kontrolü için generator'dan farklı model ailesi."""
    raise NotImplementedError
