"""Gemini'ye doğrudan Gemini Developer API ile (LLM_PROVIDER=gemini, `google-genai` SDK).

Aracı (OpenRouter) yok: ders materyali ve sorular yalnızca Google'a gider (ADR-5, ADR-7).
Ücretsiz katmanda içerik ürün geliştirmede kullanılabilir; pilot ücretli katmanla yapılır.

- Metin: `generate_content_stream`; yalnızca düşünce olmayan metin parçaları akar.
- JSON: `response_json_schema` ile şemaya bağlı çıktı, ardından Pydantic doğrulaması.
- Araç döngüsü: function calling, mod ANY (model her adımda bir araç çağırmak zorunda).
  Modelin döndürdüğü içerik geçmişe olduğu gibi eklenir; Gemini 3+'ın düşünme imzaları
  (thought signature) böylece korunur, aynı turdaki sonraki adım bunları ister.
- Her çağrının token kullanımı `usage`'a yazılır (düşünme token'ları çıktı olarak ücretlenir).
"""

import logging
from collections.abc import Iterator
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError

from app.llm.base import ChatMessage, LLMError, LLMRefusal, LLMUsage, ToolCall, ToolSpec
from app.llm.catalog import thinking_level_for

logger = logging.getLogger(__name__)

_REFUSALS = {
    types.FinishReason.SAFETY,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.SPII,
}
_FINISHED = {types.FinishReason.STOP, types.FinishReason.FINISH_REASON_UNSPECIFIED}
# Kota (429) ve geçici sunucu hataları SDK içinde üstel beklemeyle yeniden denenir.
_RETRY = types.HttpRetryOptions(attempts=3, http_status_codes=[429, 500, 502, 503, 504])


class GeminiLLMClient:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        purpose: str = "generator",
        thinking_level: str = "low",
        max_output_tokens: int = 8192,
        timeout_s: float = 90.0,
        client: Any = None,
    ) -> None:
        self._client = client or genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000), retry_options=_RETRY),
        )
        self.model = model
        self.purpose = purpose
        self.thinking_level = thinking_level_for(model, thinking_level)
        self.max_output_tokens = max_output_tokens
        self.usage: list[LLMUsage] = []

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        finish: types.FinishReason | None = None
        usage = None
        try:
            stream = self._client.models.generate_content_stream(
                model=self.model, contents=_contents(messages), config=self._config(system)
            )
            for chunk in stream:
                _raise_if_prompt_blocked(chunk)
                usage = chunk.usage_metadata or usage
                candidate = chunk.candidates[0] if chunk.candidates else None
                if candidate is None:
                    continue
                finish = candidate.finish_reason or finish
                if text := _text(candidate):
                    yield text
        except errors.APIError as exc:
            raise _to_llm_error(exc) from exc
        except httpx.HTTPError as exc:
            raise LLMError("LLM servisine bağlanılamadı.") from exc
        finally:
            self._record(usage)
        _check_finish(finish)

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        config = self._config(
            system,
            response_mime_type="application/json",
            response_json_schema=schema.model_json_schema(),
        )
        response = self._generate(_contents([{"role": "user", "content": prompt}]), config)
        candidate = response.candidates[0]
        _check_finish(candidate.finish_reason)
        try:
            return schema.model_validate_json(_text(candidate))
        except ValidationError as exc:
            raise LLMError("LLM cevabı şemaya uymuyor.") from exc

    def tool_conversation(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> "GeminiToolConversation":
        config = self._config(
            system,
            tools=[
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=tool.name,
                            description=tool.description,
                            parameters_json_schema=tool.parameters,
                        )
                        for tool in tools
                    ]
                )
            ],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY
                )
            ),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        return GeminiToolConversation(self, _contents(messages), config)

    def _config(self, system: str, **extra: Any) -> types.GenerateContentConfig:
        # Düşünme seviyesi Gemini 3 ve sonrasında var; 2.5 modelleri bütçe ister, varsayılanı kalır.
        thinking = (
            None
            if self.model.startswith("gemini-2")
            else types.ThinkingConfig(thinking_level=self.thinking_level.upper())
        )
        return types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self.max_output_tokens,
            thinking_config=thinking,
            **extra,
        )

    def _generate(
        self, contents: list[types.Content], config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as exc:
            raise _to_llm_error(exc) from exc
        except httpx.HTTPError as exc:
            raise LLMError("LLM servisine bağlanılamadı.") from exc
        self._record(response.usage_metadata)
        _raise_if_prompt_blocked(response)
        if not response.candidates:
            raise LLMError("LLM boş cevap döndürdü.")
        return response

    def _record(self, meta: types.GenerateContentResponseUsageMetadata | None) -> None:
        if meta is None:
            return
        thoughts = meta.thoughts_token_count or 0
        usage = LLMUsage(
            model=self.model,
            purpose=self.purpose,
            input_tokens=meta.prompt_token_count or 0,
            output_tokens=(meta.candidates_token_count or 0) + thoughts,
            thought_tokens=thoughts,
            cached_tokens=meta.cached_content_token_count or 0,
        )
        self.usage.append(usage)
        logger.debug("Gemini kullanımı: %s", usage)


class GeminiToolConversation:
    def __init__(
        self,
        client: GeminiLLMClient,
        contents: list[types.Content],
        config: types.GenerateContentConfig,
    ) -> None:
        self._client = client
        self._contents = contents
        self._config = config

    def step(self) -> list[ToolCall]:
        response = self._client._generate(self._contents, self._config)
        candidate = response.candidates[0]
        if candidate.finish_reason == types.FinishReason.MALFORMED_FUNCTION_CALL:
            raise LLMError("Model geçersiz bir araç çağrısı üretti.")
        _check_finish(candidate.finish_reason)
        parts = candidate.content.parts if candidate.content and candidate.content.parts else []
        calls = [
            ToolCall(
                name=part.function_call.name or "",
                args=dict(part.function_call.args or {}),
                id=part.function_call.id,
            )
            for part in parts
            if part.function_call
        ]
        if not calls:
            raise LLMError("Model araç çağırmadı.")
        # Düşünme imzaları bu içerikteki parçalarda; aynen geri gönderilmeli.
        self._contents.append(candidate.content)
        return calls

    def add_results(self, results: list[tuple[ToolCall, dict[str, Any]]]) -> None:
        self._contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=call.id, name=call.name, response=result
                        )
                    )
                    for call, result in results
                ],
            )
        )


def _contents(messages: list[ChatMessage]) -> list[types.Content]:
    return [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
    ]


def _text(candidate: types.Candidate) -> str:
    """Düşünce (thought) olmayan metin parçaları; düşünce özetleri öğrenciye gitmez."""
    parts = candidate.content.parts if candidate.content and candidate.content.parts else []
    return "".join(part.text for part in parts if part.text and not part.thought)


def _raise_if_prompt_blocked(response: types.GenerateContentResponse) -> None:
    feedback = response.prompt_feedback
    if feedback is not None and feedback.block_reason:
        raise LLMRefusal("Model bu isteği yanıtlamadı.")


def _check_finish(reason: types.FinishReason | None) -> None:
    if reason is None or reason in _FINISHED:
        return
    if reason in _REFUSALS:
        raise LLMRefusal("Model bu isteği yanıtlamadı.")
    if reason == types.FinishReason.MAX_TOKENS:
        raise LLMError("LLM cevabı uzunluk sınırında kesildi.")
    if reason == types.FinishReason.RECITATION:
        # Model kaynak metni uzun uzun aynen tekrar ettiğinde durdurulur; yerine alıntı gösterilir.
        raise LLMError("LLM cevabı kaynak metni aynen tekrar ettiği için durduruldu.")
    raise LLMError(f"LLM cevabı tamamlanamadı ({reason.value}).")


def _to_llm_error(exc: errors.APIError) -> LLMError:
    if exc.code == 429:
        return LLMError("Gemini istek ya da kota sınırına takıldı; biraz sonra tekrar deneyin.")
    if exc.code in (401, 403):
        return LLMError("Gemini API anahtarı geçersiz ya da bu modele erişimi yok.")
    if exc.code == 404:
        return LLMError("Gemini modeli bulunamadı; LLM_MODEL değerini kontrol edin.")
    logger.warning("Gemini hatası %s %s: %s", exc.code, exc.status, exc.message)
    return LLMError(f"LLM API hatası ({exc.code}).")
