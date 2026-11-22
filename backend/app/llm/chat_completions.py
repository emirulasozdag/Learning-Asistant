from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator
from typing import Any

import openai
from openai.types.chat import ChatCompletion
from openai.types.completion_usage import CompletionUsage
from pydantic import BaseModel, ValidationError

from app.core.config import OPENAI_BASE_URL
from app.llm.base import (
    ChatMessage,
    ContentPart,
    ImageInputUnsupported,
    ImagePart,
    LLMError,
    LLMRefusal,
    LLMUsage,
    ToolCall,
    ToolSpec,
)

logger = logging.getLogger(__name__)


class ChatCompletionsClient:
    """OpenAI Chat Completions protokolüyle metin, şemalı JSON ve görüntü istekleri."""

    # Görüntü parçaları gönderilir; modelin kabul etmemesi `ImageInputUnsupported` olur (#26).
    accepts_images = True

    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        model: str,
        base_url: str,
        purpose: str = "generator",
        timeout_s: float = 90.0,
    ) -> None:
        self.name = name
        self.purpose = purpose
        self.usage: list[LLMUsage] = []
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_s,
            max_retries=2,
            # OpenRouter panelinde isteklerin hangi uygulamadan geldiği görünsün.
            default_headers={"X-Title": "Interactive Learning Assistant"}
            if name == "openrouter"
            else {},
        )
        self.model = model
        self._options = (
            {"max_completion_tokens": 4000, "store": False}
            if name == "openai"
            else {"max_tokens": 4000}
        )

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        try:
            with self._client.chat.completions.create(
                model=self.model,
                **self._options,
                **({"stream_options": {"include_usage": True}} if self.name == "openai" else {}),
                messages=[{"role": "system", "content": system}, *messages],
                stream=True,
            ) as stream:
                finish_reason = None
                for chunk in stream:
                    self._record_usage(chunk.usage)
                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    finish_reason = choice.finish_reason or finish_reason
                    if choice.delta:
                        if choice.delta.refusal:
                            raise LLMRefusal("Model bu soruyu yanıtlamadı.")
                        if choice.delta.content:
                            yield choice.delta.content
        except openai.APIError as exc:
            raise _to_llm_error(exc) from exc
        _check_finish(finish_reason)

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        return self._json(system, prompt, schema)

    def complete_json_with_images[T: BaseModel](
        self, system: str, parts: list[ContentPart], schema: type[T]
    ) -> T:
        """Görüntülü istek (#26): OpenAI biçiminde metin ve `data:` URL görüntü parçaları.

        Model görüntü kabul etmiyorsa uç nokta isteği reddeder; bu `ImageInputUnsupported`
        olur (görsel iddia kontrol edilemez sayılır, türetilmiş metne düşülmez).
        """
        return self._json(system, [_content_part(part) for part in parts], schema, images=True)

    def _json[T: BaseModel](
        self, system: str, content: Any, schema: type[T], images: bool = False
    ) -> T:
        try:
            response = self._complete(
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
                raise ImageInputUnsupported(
                    f"{self.model} görüntü girdisi kabul etmiyor; görsel iddia kontrol edilemedi."
                ) from exc
            raise _to_llm_error(exc) from exc
        try:
            return schema.model_validate_json(response.choices[0].message.content or "")
        except ValidationError as exc:
            raise LLMError("LLM cevabı şemaya uymuyor.") from exc

    def _complete(self, **kwargs: Any) -> ChatCompletion:
        response = self._client.chat.completions.create(model=self.model, **self._options, **kwargs)
        self._record_usage(response.usage)
        if not response.choices:
            raise LLMError("Model cevap döndürmedi.")
        choice = response.choices[0]
        if choice.message.refusal:
            raise LLMRefusal("Model bu isteği yanıtlamadı.")
        _check_finish(choice.finish_reason, expected="tool_calls" if "tools" in kwargs else "stop")
        return response

    def _record_usage(self, usage: CompletionUsage | None) -> None:
        if usage is not None:
            self.usage.append(
                LLMUsage(
                    model=self.model,
                    purpose=self.purpose,
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens,
                    thought_tokens=getattr(usage.completion_tokens_details, "reasoning_tokens", 0)
                    or 0,
                    cached_tokens=getattr(usage.prompt_tokens_details, "cached_tokens", 0) or 0,
                )
            )


class OpenAIClient(ChatCompletionsClient):
    def __init__(self, *, api_key: str, model: str, purpose: str, timeout_s: float) -> None:
        super().__init__(
            name="openai",
            api_key=api_key,
            model=model,
            base_url=OPENAI_BASE_URL,
            purpose=purpose,
            timeout_s=timeout_s,
        )

    def tool_conversation(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> OpenAIToolConversation:
        return OpenAIToolConversation(self, system, messages, tools)


class OpenAIToolConversation:
    def __init__(
        self, client: OpenAIClient, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> None:
        self._client = client
        self._messages: list[dict] = [{"role": "system", "content": system}, *messages]
        self._tools = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def step(self) -> list[ToolCall]:
        try:
            response = self._client._complete(
                messages=self._messages,
                tools=self._tools,
                tool_choice="required",
            )
        except openai.APIError as exc:
            raise _to_llm_error(exc) from exc
        raw_calls = response.choices[0].message.tool_calls
        if not raw_calls:
            raise LLMError("Model araç çağırmadı.")
        calls = []
        for call in raw_calls:
            if call.type != "function" or not call.id or not call.function.name:
                raise LLMError("Model geçersiz bir araç çağrısı üretti.")
            try:
                args = json.loads(call.function.arguments)
            except json.JSONDecodeError as exc:
                raise LLMError("Model geçersiz araç argümanları üretti.") from exc
            if not isinstance(args, dict):
                raise LLMError("Model geçersiz araç argümanları üretti.")
            calls.append(ToolCall(call.function.name, args, call.id))
        self._messages.append(
            {
                "role": "assistant",
                "tool_calls": [call.model_dump(exclude_none=True) for call in raw_calls],
            }
        )
        return calls

    def add_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        self._messages.extend(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
            for call, result in results
        )


def _check_finish(reason: str | None, expected: str = "stop") -> None:
    if reason == "content_filter":
        raise LLMRefusal("Model bu isteği yanıtlamadı.")
    if reason == "length":
        raise LLMError("LLM cevabı uzunluk sınırında kesildi.")
    if reason != expected:
        raise LLMError("Model beklenen cevabı tamamlamadı.")


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
            return LLMError("Model sağlayıcısı hesabında yeterli kredi yok.")
        logger.warning(
            "LLM API hatası %s (code=%s, param=%s, request_id=%s)",
            exc.status_code,
            exc.code,
            exc.param,
            exc.request_id,
        )
        return LLMError(f"LLM API hatası ({exc.status_code}).")
    return LLMError("LLM servisine bağlanılamadı.")
