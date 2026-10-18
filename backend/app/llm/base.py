from collections.abc import Iterator
from typing import Literal, Protocol, TypedDict

from pydantic import BaseModel


class LLMError(Exception):
    """LLM'den kullanılabilir bir cevap alınamadı (ağ, kota, anahtar, kesilme)."""


class LLMRefusal(LLMError):
    """Model güvenlik gerekçesiyle cevap vermedi."""


class ChatMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str


class LLMClient(Protocol):
    """Sağlayıcıdan bağımsız arayüz: akışlı metin ve şemaya uyan JSON."""

    name: str
    model: str

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        """Cevabı parça parça üretir. Hata olursa LLMError fırlatır."""
        ...

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T: ...
