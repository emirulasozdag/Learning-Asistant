"""Gemini istemcisi: SDK'nın gerçek tipleriyle kurulan sahte cevaplar (ağ yok)."""

from collections.abc import Iterator

import pytest
from google.genai import errors, types
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import LLMError, LLMRefusal, LLMUsage, ToolCall, ToolSpec
from app.llm.catalog import estimate_cost_usd, thinking_level_for
from app.llm.gateway import LLMRole, select_client, select_orchestrator
from app.llm.gemini import GeminiLLMClient


class FakeModels:
    def __init__(
        self,
        responses: list[types.GenerateContentResponse] | None = None,
        stream: list[types.GenerateContentResponse] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.stream = list(stream or [])
        self.error = error
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        if self.error:
            raise self.error
        return self.responses.pop(0)

    def generate_content_stream(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})

        def chunks() -> Iterator[types.GenerateContentResponse]:
            yield from self.stream
            if self.error:
                raise self.error

        return chunks()


class FakeGenAI:
    def __init__(self, models: FakeModels) -> None:
        self.models = models


def gemini(models: FakeModels, **kwargs) -> GeminiLLMClient:
    kwargs.setdefault("model", "gemini-3.8-flash")
    return GeminiLLMClient(api_key="test", client=FakeGenAI(models), **kwargs)


def response(
    *parts: types.Part,
    finish: types.FinishReason | None = types.FinishReason.STOP,
    usage: types.GenerateContentResponseUsageMetadata | None = None,
) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=list(parts)), finish_reason=finish
            )
        ],
        usage_metadata=usage,
    )


USAGE = types.GenerateContentResponseUsageMetadata(
    prompt_token_count=1000,
    candidates_token_count=200,
    thoughts_token_count=50,
    cached_content_token_count=400,
)


def test_stream_yields_answer_text_but_not_thoughts_and_records_usage() -> None:
    models = FakeModels(
        stream=[
            response(types.Part(text="plan yapıyorum", thought=True), finish=None),
            response(types.Part(text="Sağ yarı elenir "), finish=None),
            response(types.Part(text="[S1]."), usage=USAGE),
        ]
    )
    llm = gemini(models)

    chunks = list(llm.stream_text("sistem", [{"role": "user", "content": "Neden?"}]))

    assert chunks == ["Sağ yarı elenir ", "[S1]."]
    call = models.calls[0]
    assert call["config"].system_instruction == "sistem"
    assert call["contents"][0].role == "user"
    assert llm.usage == [
        LLMUsage(
            model="gemini-3.8-flash",
            purpose="generator",
            input_tokens=1000,
            output_tokens=250,  # düşünme token'ları çıktı olarak ücretlenir
            thought_tokens=50,
            cached_tokens=400,
        )
    ]


def test_history_roles_are_mapped_to_gemini_roles() -> None:
    models = FakeModels(stream=[response(types.Part(text="ok"))])

    list(
        gemini(models).stream_text(
            "s",
            [
                {"role": "user", "content": "a"},
                {"role": "assistant", "content": "b"},
                {"role": "user", "content": "c"},
            ],
        )
    )

    assert [c.role for c in models.calls[0]["contents"]] == ["user", "model", "user"]


@pytest.mark.parametrize(
    ("finish", "error"),
    [
        (types.FinishReason.MAX_TOKENS, LLMError),
        (types.FinishReason.SAFETY, LLMRefusal),
        (types.FinishReason.PROHIBITED_CONTENT, LLMRefusal),
        (types.FinishReason.OTHER, LLMError),
    ],
)
def test_unfinished_stream_raises(finish: types.FinishReason, error: type[Exception]) -> None:
    models = FakeModels(stream=[response(types.Part(text="yarım"), finish=finish)])

    with pytest.raises(error):
        list(gemini(models).stream_text("s", [{"role": "user", "content": "?"}]))


def test_recitation_is_a_provider_failure_not_a_refusal() -> None:
    """Model kaynağı aynen tekrar edince durur; cevap yerine alıntı gösterilebilsin."""
    models = FakeModels(
        stream=[response(types.Part(text="..."), finish=types.FinishReason.RECITATION)]
    )

    with pytest.raises(LLMError) as raised:
        list(gemini(models).stream_text("s", [{"role": "user", "content": "?"}]))

    assert not isinstance(raised.value, LLMRefusal)


def test_blocked_prompt_is_a_refusal() -> None:
    blocked = types.GenerateContentResponse(
        prompt_feedback=types.GenerateContentResponsePromptFeedback(
            block_reason=types.BlockedReason.SAFETY
        )
    )

    with pytest.raises(LLMRefusal):
        list(
            gemini(FakeModels(stream=[blocked])).stream_text(
                "s", [{"role": "user", "content": "?"}]
            )
        )


@pytest.mark.parametrize(
    ("code", "status", "expected"),
    [
        (429, "RESOURCE_EXHAUSTED", "kota"),
        (403, "PERMISSION_DENIED", "anahtarı"),
        (404, "NOT_FOUND", "LLM_MODEL"),
        (500, "INTERNAL", "(500)"),
    ],
)
def test_api_errors_become_llm_errors(code: int, status: str, expected: str) -> None:
    error = errors.APIError(code, {"error": {"code": code, "message": "x", "status": status}})

    with pytest.raises(LLMError, match=expected):
        list(gemini(FakeModels(error=error)).stream_text("s", [{"role": "user", "content": "?"}]))


class Verdict(BaseModel):
    supported: bool
    reason: str


def test_complete_json_requests_the_schema_and_validates_the_answer() -> None:
    models = FakeModels(
        responses=[response(types.Part(text='{"supported": true, "reason": "S1"}'))]
    )

    result = gemini(models).complete_json("s", "p", Verdict)

    config = models.calls[0]["config"]
    assert result == Verdict(supported=True, reason="S1")
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == Verdict.model_json_schema()


def test_complete_json_rejects_output_that_does_not_match_the_schema() -> None:
    models = FakeModels(responses=[response(types.Part(text='{"supported": "belki"}'))])

    with pytest.raises(LLMError, match="şemaya"):
        gemini(models).complete_json("s", "p", Verdict)


def test_unsupported_thinking_level_uses_the_nearest_supported_one() -> None:
    models = FakeModels(stream=[response(types.Part(text="ok"))])
    llm = gemini(models, model="gemini-3.8-flash", thinking_level="minimal")

    list(llm.stream_text("s", [{"role": "user", "content": "?"}]))

    assert llm.thinking_level == "low"  # 3.8 Flash "minimal" kabul etmez
    assert models.calls[0]["config"].thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert thinking_level_for("gemini-3.5-flash-lite", "minimal") == "minimal"
    assert thinking_level_for("bilinmeyen-model", "minimal") == "minimal"


TOOLS = [
    ToolSpec(
        "answer_from_course",
        "Ders materyalinden cevap",
        {"type": "object", "properties": {"question": {"type": "string"}}},
    ),
    ToolSpec("finish", "Bitir", {"type": "object", "properties": {}}),
]


def test_tool_conversation_forces_a_call_and_keeps_thought_signatures() -> None:
    call_part = types.Part(
        function_call=types.FunctionCall(
            id="c1", name="answer_from_course", args={"question": "İkili arama nedir?"}
        ),
        thought_signature=b"imza",
    )
    models = FakeModels(
        responses=[
            response(call_part, usage=USAGE),
            response(types.Part(function_call=types.FunctionCall(id="c2", name="finish", args={}))),
        ]
    )
    llm = gemini(models, model="gemini-3.5-flash-lite", purpose="orchestrator")

    conversation = llm.tool_conversation("s", [{"role": "user", "content": "ikili arama?"}], TOOLS)
    first = conversation.step()
    conversation.add_results([(first[0], {"status": "answered", "citations": 2})])
    second = conversation.step()

    config = models.calls[0]["config"]
    assert first == [ToolCall("answer_from_course", {"question": "İkili arama nedir?"}, "c1")]
    assert second == [ToolCall("finish", {}, "c2")]
    assert config.tool_config.function_calling_config.mode == types.FunctionCallingConfigMode.ANY
    assert config.automatic_function_calling.disable is True
    assert [d.name for d in config.tools[0].function_declarations] == [
        "answer_from_course",
        "finish",
    ]
    # İkinci istek: modelin içeriği imzasıyla aynen, ardından aracın sonucu.
    contents = models.calls[1]["contents"]
    assert contents[1].parts[0].thought_signature == b"imza"
    result = contents[2].parts[0].function_response
    assert contents[2].role == "user"
    assert (result.id, result.name, result.response) == (
        "c1",
        "answer_from_course",
        {"status": "answered", "citations": 2},
    )
    assert llm.usage[0].purpose == "orchestrator"


def test_tool_step_without_a_call_is_an_error() -> None:
    models = FakeModels(responses=[response(types.Part(text="Kendim cevaplayayım: ..."))])
    conversation = gemini(models).tool_conversation("s", [{"role": "user", "content": "?"}], TOOLS)

    with pytest.raises(LLMError, match="araç"):
        conversation.step()


def test_malformed_function_call_is_an_error() -> None:
    models = FakeModels(responses=[response(finish=types.FinishReason.MALFORMED_FUNCTION_CALL)])
    conversation = gemini(models).tool_conversation("s", [{"role": "user", "content": "?"}], TOOLS)

    with pytest.raises(LLMError, match="geçersiz"):
        conversation.step()


def test_cost_is_estimated_from_the_price_table() -> None:
    # 600 yeni girdi × 0,75 + 400 önbellek × 0,075 + 250 çıktı × 3,75 (USD / 1M token)
    assert estimate_cost_usd("gemini-3.8-flash", 1000, 250, 400) == pytest.approx(0.0014175)
    assert estimate_cost_usd("bilinmeyen-model", 1000, 250) is None


def test_gateway_picks_role_specific_gemini_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "llm_api_key", "test")
    monkeypatch.setattr(settings, "llm_model", "")
    monkeypatch.setattr(settings, "llm_orchestrator_model", "")

    generator = select_client()
    orchestrator = select_orchestrator()

    assert isinstance(generator, GeminiLLMClient) and generator.model == "gemini-3.8-flash"
    assert orchestrator is not None and orchestrator.model == "gemini-3.5-flash-lite"
    assert orchestrator.thinking_level == "minimal"  # type: ignore[attr-defined]


def test_gateway_has_no_orchestrator_without_tool_calling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "llm_api_key", "test")
    monkeypatch.setattr(settings, "llm_model", "")

    assert select_client(LLMRole.GENERATOR).model == "anthropic/claude-opus-5.5"  # type: ignore[union-attr]
    assert select_orchestrator() is None
