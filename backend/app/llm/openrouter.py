import json
import logging
from collections.abc import Iterator

import openai
from pydantic import BaseModel, ValidationError

from app.llm.base import ChatMessage, LLMError, LLMRefusal

logger = logging.getLogger(__name__)


class OpenRouterLLMClient:
    """OpenRouter (OpenAI uyumlu API) üzerinden herhangi bir model: Claude, GPT, Gemini..."""

    name = "openrouter"

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
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
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
            raise _to_llm_error(exc) from exc
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise LLMRefusal("Model bu isteği yanıtlamadı.")
        try:
            return schema.model_validate(json.loads(choice.message.content or ""))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise LLMError("LLM cevabı şemaya uymuyor.") from exc


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
