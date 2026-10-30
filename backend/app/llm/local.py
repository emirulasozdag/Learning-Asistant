"""Yerel model: OpenAI uyumlu yerel uç nokta (ör. Ollama `http://localhost:11434/v1`).

Yapılandırılmamışsa her çağrı `LocalRouteUnavailable` fırlatır; hosted'a düşülmez (ADR-8).
"""

from collections.abc import Iterator

from pydantic import BaseModel

from app.llm.base import ChatMessage
from app.llm.openrouter import OpenRouterLLMClient
from app.llm.routing import LocalRouteUnavailable

NOT_CONFIGURED = (
    "Bu iş yerel modele yönlendirildi ama yerel model yapılandırılmamış "
    "(LLM_LOCAL_BASE_URL, LLM_LOCAL_MODEL); veri hosted modele gönderilmedi."
)


class LocalLLMClient:
    """Gizli / offline işler için yerel model."""

    name = "local"

    def __init__(self, base_url: str = "", model: str = "") -> None:
        self.model = model or "local-unconfigured"
        self._client = (
            OpenRouterLLMClient(api_key="local", model=model, base_url=base_url)
            if base_url and model
            else None
        )

    @property
    def configured(self) -> bool:
        return self._client is not None

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        if self._client is None:
            raise LocalRouteUnavailable(NOT_CONFIGURED)
        yield from self._client.stream_text(system, messages)

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        if self._client is None:
            raise LocalRouteUnavailable(NOT_CONFIGURED)
        return self._client.complete_json(system, prompt, schema)
