import base64
import logging
from collections.abc import Iterator
from time import monotonic
from typing import Any

import anthropic
from pydantic import BaseModel

from app.llm.base import ChatMessage, ContentPart, ImagePart, LLMError, LLMRefusal
from app.llm.deadline import (
    TutorTurnDeadlineExceeded,
    check_tutor_turn_deadline,
    request_timed_out_at_deadline,
    request_timeout,
)

logger = logging.getLogger(__name__)


class AnthropicLLMClient:
    """Claude'a doğrudan Anthropic API ile (LLM_PROVIDER=anthropic)."""

    name = "anthropic"
    # Anthropic modelleri görüntü girdisi kabul eder (#26).
    accepts_images = True

    def __init__(
        self, api_key: str, model: str, effort: str = "medium", timeout_s: float = 60.0
    ) -> None:
        self.timeout_s = timeout_s
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=2)
        self.model = model
        self.effort = effort

    def _request_client(self) -> anthropic.Anthropic:
        timeout_s, deadline_active = request_timeout(self.timeout_s)
        if deadline_active:
            return self._client.with_options(timeout=timeout_s, max_retries=0)
        return self._client

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        request_started_at = monotonic()
        try:
            with self._request_client().beta.messages.stream(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=messages,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    check_tutor_turn_deadline()
                    yield text
                final = stream.get_final_message()
        except anthropic.APIError as exc:
            if isinstance(exc, anthropic.APITimeoutError) and request_timed_out_at_deadline(
                self.timeout_s, request_started_at
            ):
                raise TutorTurnDeadlineExceeded from exc
            check_tutor_turn_deadline()
            raise _to_llm_error(exc) from exc
        check_tutor_turn_deadline()
        if final.stop_reason == "refusal":
            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
        if final.stop_reason == "max_tokens":
            raise LLMError("LLM cevabı uzunluk sınırında kesildi.")

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        return self._parse(system, prompt, schema)

    def complete_json_with_images[T: BaseModel](
        self, system: str, parts: list[ContentPart], schema: type[T]
    ) -> T:
        """Görüntülü istek (#26): metin ve base64 görüntü blokları tek kullanıcı mesajında."""
        return self._parse(system, [_block(part) for part in parts], schema)

    def _parse[T: BaseModel](self, system: str, content: Any, schema: type[T]) -> T:
        request_started_at = monotonic()
        try:
            response = self._request_client().beta.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": content}],
                output_format=schema,
                output_config={"effort": self.effort},
                # Güvenlik sınıflandırıcısı reddederse istek sunucu tarafında uygun modele yönlenir.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.APIError as exc:
            if isinstance(exc, anthropic.APITimeoutError) and request_timed_out_at_deadline(
                self.timeout_s, request_started_at
            ):
                raise TutorTurnDeadlineExceeded from exc
            check_tutor_turn_deadline()
            raise _to_llm_error(exc) from exc
        check_tutor_turn_deadline()

        if response.stop_reason == "refusal":
            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
        if response.stop_reason == "max_tokens" or response.parsed_output is None:
            raise LLMError("LLM cevabı eksik ya da şemaya uymuyor.")
        return response.parsed_output


def _block(part: ContentPart) -> dict[str, Any]:
    if isinstance(part, ImagePart):
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": part.mime_type,
                "data": base64.b64encode(part.data).decode("ascii"),
            },
        }
    return {"type": "text", "text": part.text}


def _to_llm_error(exc: anthropic.APIError) -> LLMError:
    if isinstance(exc, anthropic.AuthenticationError):
        return LLMError("LLM API anahtarı geçersiz.")
    if isinstance(exc, anthropic.RateLimitError):
        return LLMError("LLM istek sınırına takıldı; biraz sonra tekrar deneyin.")
    if isinstance(exc, anthropic.APIStatusError):
        logger.warning("LLM API hatası %s (request id %s)", exc.status_code, exc.request_id)
        return LLMError(f"LLM API hatası ({exc.status_code}).")
    return LLMError("LLM servisine bağlanılamadı.")
