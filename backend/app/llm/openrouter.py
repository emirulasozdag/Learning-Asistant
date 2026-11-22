import base64
import json
import logging
from collections.abc import Iterator
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from app.llm.base import (
    ChatMessage,
    ContentPart,
    ImageInputUnsupported,
    ImagePart,
    LLMError,
    LLMRefusal,
)

logger = logging.getLogger(__name__)


class OpenRouterLLMClient:
    """OpenRouter (OpenAI uyumlu API) üzerinden herhangi bir model: Claude, GPT, Gemini..."""

    name = "openrouter"
    # Görüntü parçaları gönderilir; modelin kabul etmemesi `ImageInputUnsupported` olur (#26).
    accepts_images = True

    def __init__(self, api_key: str, model: str, base_url: str, max_tokens: int = 4000) -> None:
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=90.0,
            max_retries=2,
            # OpenRouter panelinde isteklerin hangi uygulamadan geldiği görünsün.
            default_headers={"X-Title": "Interactive Learning Assistant"},
        )
        self.model = model
        self.max_tokens = max_tokens

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        try:
            stream = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "system", "content": system}, *messages],
                stream=True,
            )
            finish_reason = None
            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.delta and choice.delta.content:
                    yield choice.delta.content
                finish_reason = choice.finish_reason or finish_reason
        except openai.APIError as exc:
            raise _to_llm_error(exc) from exc
        if finish_reason == "content_filter":
            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
        if finish_reason == "length":
            raise LLMError("LLM cevabı uzunluk sınırında kesildi.")

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        return self._json(system, prompt, schema)

    def complete_json_with_images[T: BaseModel](
        self, system: str, parts: list[ContentPart], schema: type[T]
    ) -> T:
        """Görüntülü istek (#26): OpenAI biçiminde metin ve `data:` URL görüntü parçaları.

        Model görüntü kabul etmiyorsa uç nokta isteği reddeder; bu `ImageInputUnsupported`
        olur (görsel iddia kontrol edilemez sayılır, türetilmiş metne düşülmez).
        """
        content = [_content_part(part) for part in parts]
        try:
            return self._json(system, content, schema, images=True)
        except _ImageRejected as exc:
            raise ImageInputUnsupported(
                f"{self.model} görüntü girdisi kabul etmiyor; görsel iddia kontrol edilemedi."
            ) from exc

    def _json[T: BaseModel](
        self, system: str, content: Any, schema: type[T], images: bool = False
    ) -> T:
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": False,
                        "schema": schema.model_json_schema(),
                    },
                },
            )
        except openai.APIError as exc:
            if images and _rejects_images(exc):
                raise _ImageRejected from exc
            raise _to_llm_error(exc) from exc
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise LLMRefusal("Model bu isteği yanıtlamadı.")
        if choice.finish_reason == "length":
            raise LLMError("LLM cevabı uzunluk sınırında kesildi.")
        try:
            return schema.model_validate(json.loads(choice.message.content or ""))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError("LLM cevabı şemaya uymuyor.") from exc


class _ImageRejected(Exception):
    """Uç nokta görüntülü isteği modelin görüntü desteği olmadığı için reddetti."""


def _rejects_images(exc: openai.APIError) -> bool:
    """OpenRouter görüntü desteği olmayan modelde 404 ("No endpoints found that support image
    input"), OpenAI uyumlu yerel sunucular 400 döndürür; ikisinde de ileti görüntüden söz eder."""
    return (
        isinstance(exc, openai.APIStatusError)
        and exc.status_code in (400, 404, 415, 422)
        and "image" in str(exc.message).lower()
    )


def _content_part(part: ContentPart) -> dict[str, Any]:
    if isinstance(part, ImagePart):
        data = base64.b64encode(part.data).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:{part.mime_type};base64,{data}"}}
    return {"type": "text", "text": part.text}


def _to_llm_error(exc: openai.APIError) -> LLMError:
    if isinstance(exc, openai.AuthenticationError):
        return LLMError("LLM API anahtarı geçersiz.")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("LLM istek sınırına takıldı; biraz sonra tekrar deneyin.")
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code == 402:
            return LLMError("OpenRouter hesabında yeterli kredi yok.")
        logger.warning("OpenRouter hatası %s: %s", exc.status_code, exc.message)
        return LLMError(f"LLM API hatası ({exc.status_code}).")
    return LLMError("LLM servisine bağlanılamadı.")
