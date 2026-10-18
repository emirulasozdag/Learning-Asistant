import logging
from collections.abc import Iterator

import anthropic
from pydantic import BaseModel

from app.llm.base import ChatMessage, LLMError, LLMRefusal

logger = logging.getLogger(__name__)


class AnthropicLLMClient:
    """Claude'a doğrudan Anthropic API ile (LLM_PROVIDER=anthropic)."""

    name = "anthropic"

    def __init__(self, api_key: str, model: str, effort: str = "medium") -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)
        self.model = model
        self.effort = effort

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        try:
            with self._client.beta.messages.stream(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=messages,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                yield from stream.text_stream
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            raise _to_llm_error(exc) from exc
        if final.stop_reason == "refusal":
            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
        if final.stop_reason == "max_tokens":
            raise LLMError("LLM cevabı uzunluk sınırında kesildi.")

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": self.effort},
                # Güvenlik sınıflandırıcısı reddederse istek sunucu tarafında uygun modele yönlenir.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as exc:
            raise _to_llm_error(exc) from exc

        if response.stop_reason == "refusal":
            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMError("LLM cevabı eksik ya da şemaya uymuyor.")
        return response.parsed_output


def _to_llm_error(exc: anthropic.APIError) -> LLMError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("LLM API anahtarı geçersiz.")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("LLM istek sınırına takıldı; biraz sonra tekrar deneyin.")
    if isinstance(exc, anthropic.APIStatusError):
        logger.warning("LLM API hatası %s (request id %s)", exc.status_code, exc.request_id)
        return LLMError(f"LLM API hatası ({exc.status_code}).")
    return LLMError("LLM servisine bağlanılamadı.")
