from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypedDict, runtime_checkable

from pydantic import BaseModel

from app.llm.catalog import estimate_cost_usd


class LLMError(Exception):
    """LLM'den kullanılabilir bir cevap alınamadı (ağ, kota, anahtar, kesilme)."""


class LLMRefusal(LLMError):
    """Model güvenlik gerekçesiyle cevap vermedi."""


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMUsage:
    """Tek bir model çağrısının token kullanımı. `output_tokens` düşünme token'larını içerir
    (ücretlendirme böyle); `thought_tokens` ayrıca gösterilir."""

    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    thought_tokens: int = 0
    cached_tokens: int = 0

    @property
    def cost_usd(self) -> float | None:
        return estimate_cost_usd(
            self.model, self.input_tokens, self.output_tokens, self.cached_tokens
        )


class LLMClient(Protocol):
    """Sağlayıcıdan bağımsız arayüz: akışlı metin ve şemaya uyan JSON."""

    name: str
    model: str

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        """Cevabı parça parça üretir. Hata olursa LLMError fırlatır."""
        ...

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T: ...


@dataclass(frozen=True)
class ToolSpec:
    """Modele tanıtılan araç: ad, ne zaman kullanılacağı ve argümanların JSON şeması."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    # Sağlayıcının çağrı kimliği (paralel çağrılarda sonucu eşlemek için); yoksa None.
    id: str | None = None


class ToolConversation(Protocol):
    """Bir turdaki araç döngüsü. Sağlayıcıya özgü durum (ör. Gemini'nin düşünme imzaları)
    bu nesnede kalır; çağıran yalnızca çağrıları ve sonuçları görür."""

    def step(self) -> list[ToolCall]:
        """Modelin bir sonraki araç çağrıları (en az bir tane). Hata olursa LLMError."""
        ...

    def add_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None: ...


@runtime_checkable
class ToolCallingClient(Protocol):
    """Araç çağırabilen istemci. Model her adımda en az bir araç çağırmak zorundadır; serbest
    metin cevabı yoktur (öğrenciye giden içerik yalnızca araçlardan gelir, ADR-7)."""

    name: str
    model: str
    usage: list[LLMUsage]

    def tool_conversation(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> ToolConversation: ...
