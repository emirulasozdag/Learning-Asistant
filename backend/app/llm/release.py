"""Model çağrısından hemen önce veritabanı işlemini kapatan istemci sarmalayıcısı (#88).

Bir AI Tutor turu okuma (arama, sohbet geçmişi, kaynak parçaları) ile model çağrılarını
(orkestratör, yeniden sıralama, üretim, pratik kontrolü) iç içe yapar. Okuma bir işlem açar;
model çağrısı onlarca saniye sürebilir. Sarmalayıcı her çağrıdan önce `release`i (ör.
`db.commit`) çağırır: bağlantı "idle in transaction" beklemez, kilit tutulmaz. Sonraki okuma
yeni, kısa bir işlem açar. Oturum `expire_on_commit=False` olduğu için yüklenmiş nesneler
kullanılmaya devam eder.

Sarmalanan istemcinin diğer öznitelikleri (`name`, `model`, `usage` …) olduğu gibi okunur.
"""

from collections.abc import Callable, Iterator
from typing import Any

from pydantic import BaseModel

from app.llm.base import ChatMessage, ToolCall, ToolSpec

Release = Callable[[], None]


class ReleasingClient:
    def __init__(self, inner: Any, release: Release) -> None:
        self._inner = inner
        self._release = release

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        self._release()
        return self._inner.stream_text(system, messages)

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        self._release()
        return self._inner.complete_json(system, prompt, schema)

    def tool_conversation(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> "_ReleasingConversation":
        return _ReleasingConversation(
            self._inner.tool_conversation(system, messages, tools), self._release
        )


class _ReleasingConversation:
    def __init__(self, inner: Any, release: Release) -> None:
        self._inner = inner
        self._release = release

    def step(self) -> list[ToolCall]:
        self._release()
        return self._inner.step()

    def add_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        self._inner.add_results(results)


def releasing[C](client: C | None, release: Release) -> C | None:
    """İstemciyi sarar; None ise None (model yapılandırılmamış)."""
    return None if client is None else ReleasingClient(client, release)  # type: ignore[return-value]
