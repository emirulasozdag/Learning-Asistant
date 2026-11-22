import json
from functools import partial

import httpx2
import openai
import pytest
from pydantic import BaseModel

from app.core.config import settings
from app.llm.base import ImagePart, LLMError, LLMRefusal, ToolCall, ToolSpec
from app.llm.gateway import (
    JudgeConfigError,
    LLMRole,
    select_client,
    select_judge_client,
    select_orchestrator,
)
from app.llm.routing import DataClass
from app.tutor.tools import ANSWER_FROM_COURSE, FINISH


class Verdict(BaseModel):
    supported: bool


@pytest.fixture
def wire(monkeypatch):
    requests = []
    replies = []

    def respond(request):
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert "X-Title" not in request.headers
        body = json.loads(request.content)
        assert body["store"] is False
        assert body["max_completion_tokens"] > 0 and "max_tokens" not in body
        requests.append((request.headers["Authorization"], body))
        return replies.pop(0)

    with httpx2.Client(transport=httpx2.MockTransport(respond)) as http:
        monkeypatch.setattr(openai, "OpenAI", partial(openai.OpenAI, http_client=http))
        monkeypatch.setattr(settings, "llm_provider", "openai")
        monkeypatch.setattr(settings, "llm_model", "")
        monkeypatch.setattr(settings, "llm_orchestrator_model", "")
        monkeypatch.setattr(settings, "llm_api_key", "test-generator")
        monkeypatch.setattr(settings, "llm_base_url", "https://routing.invalid")
        monkeypatch.setenv("OPENAI_BASE_URL", "https://routing.invalid")
        yield requests, replies


def completion(message, reason="stop"):
    return httpx2.Response(
        200,
        json={
            "id": "completion",
            "object": "chat.completion",
            "created": 1,
            "model": "gpt-5.4-mini",
            "choices": [
                {"index": 0, "finish_reason": reason, "message": {"role": "assistant", **message}}
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 5, "total_tokens": 14},
        },
    )


def test_stream_and_role_selection(wire, monkeypatch):
    requests, replies = wire
    chunk = {"id": "s", "object": "chat.completion.chunk", "created": 1, "model": "gpt-5.4-mini"}
    events = [
        {
            **chunk,
            "choices": [{"index": 0, "delta": {"content": "Merhaba"}, "finish_reason": None}],
        },
        {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
        {
            **chunk,
            "choices": [],
            "usage": {"prompt_tokens": 6, "completion_tokens": 1, "total_tokens": 7},
        },
    ]
    replies.append(
        httpx2.Response(
            200,
            headers={"content-type": "text/event-stream"},
            text="".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n",
        )
    )
    client = select_client()
    assert settings.llm_endpoint == "https://api.openai.com/v1"
    assert client.name == "openai" and client.model == "gpt-5.4-mini"
    assert list(client.stream_text("system", [{"role": "user", "content": "hi"}])) == ["Merhaba"]
    assert client.usage[0].output_tokens == 1
    auth, body = requests[0]
    assert auth == "Bearer test-generator"
    assert body["stream_options"] == {"include_usage": True}
    monkeypatch.setattr(settings, "llm_orchestrator_model", "routing-model")
    monkeypatch.setattr(settings, "llm_checker_model", "checking-model")
    assert select_orchestrator().model == select_client(LLMRole.RERANKER).model == "routing-model"
    assert select_client(LLMRole.CHECKER).model == "checking-model"
    assert select_client(data=DataClass.PERSONAL).name == "local"
    monkeypatch.setattr(settings, "llm_api_key", "")
    assert select_client() is None


def test_judge_uses_own_key_and_image(wire, monkeypatch):
    requests, replies = wire
    monkeypatch.setattr(settings, "judge_provider", "openai")
    monkeypatch.setattr(settings, "judge_model", "gpt-5.4")
    monkeypatch.setattr(settings, "judge_api_key", "test-judge")
    monkeypatch.setattr(settings, "judge_base_url", "https://judge.invalid")
    with pytest.raises(JudgeConfigError, match="aynı model ailesinden"):
        select_judge_client()
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    replies.append(completion({"content": '{"supported":true}'}))
    judge = select_judge_client()
    assert judge.complete_json_with_images("s", [ImagePart(b"img", "image/png")], Verdict).supported
    auth, body = requests[0]
    assert auth == "Bearer test-judge"
    assert body["model"] == "gpt-5.4"
    assert body["response_format"]["json_schema"]["schema"] == Verdict.model_json_schema()
    assert body["messages"][1]["content"][0]["image_url"]["url"] == "data:image/png;base64,aW1n"


def test_tutor_round_trip(wire):
    requests, replies = wire
    function = {"name": "answer_from_course", "arguments": '{"question":"How does sorting work?"}'}
    call = {"id": "c1", "type": "function", "function": function}
    finish = {"id": "c2", "type": "function", "function": {"name": "finish", "arguments": "{}"}}
    replies.extend(
        [
            completion({"tool_calls": [call]}, "tool_calls"),
            completion({"tool_calls": [finish]}, "tool_calls"),
        ]
    )
    conversation = select_orchestrator().tool_conversation(
        "s",
        [{"role": "user", "content": "q"}],
        [ANSWER_FROM_COURSE.spec(), FINISH.spec()],
    )
    calls = conversation.step()
    assert calls == [ToolCall("answer_from_course", {"question": "How does sorting work?"}, "c1")]
    conversation.add_results([(calls[0], {"status": "answered"})])
    assert conversation.step() == [ToolCall("finish", {}, "c2")]
    body = requests[1][1]
    assert body["tool_choice"] == "required"
    assert body["tools"][0]["function"]["parameters"] == ANSWER_FROM_COURSE.spec().parameters
    assert body["messages"][-2]["tool_calls"] == [call]
    result = body["messages"][-1]
    assert result["role"] == "tool" and result["tool_call_id"] == "c1"
    assert json.loads(result["content"]) == {"status": "answered"}


@pytest.mark.parametrize("arguments", ["{", "[]"])
def test_malformed_tool_arguments_fail(wire, arguments):
    _, replies = wire
    call = {"id": "c", "type": "function", "function": {"name": "lookup", "arguments": arguments}}
    replies.append(completion({"tool_calls": [call]}, "tool_calls"))
    conversation = select_orchestrator().tool_conversation(
        "s", [], [ToolSpec("lookup", "Find notes", {"type": "object"})]
    )
    with pytest.raises(LLMError, match="argüman"):
        conversation.step()


def test_invalid_key_is_reported(wire):
    _, replies = wire
    replies.append(httpx2.Response(401, json={"error": {"message": "Invalid API key"}}))
    with pytest.raises(LLMError, match="anahtarı geçersiz"):
        select_client().complete_json("s", "q", Verdict)


def test_rejected_request_logs_provider_code_parameter_and_request_id(wire, caplog):
    _, replies = wire
    replies.append(
        httpx2.Response(
            400,
            headers={"x-request-id": "req-test"},
            json={
                "error": {
                    "code": "invalid_function_parameters",
                    "param": "tools[0]",
                    "message": "invalid schema",
                }
            },
        )
    )
    with pytest.raises(LLMError, match="400"):
        select_client().complete_json("s", "q", Verdict)
    assert all(
        value in caplog.text for value in ("invalid_function_parameters", "tools[0]", "req-test")
    )


@pytest.mark.parametrize(
    ("message", "reason", "error"),
    [
        ({"content": '{"supported":true}'}, "length", LLMError),
        ({"content": None, "refusal": "declined"}, "stop", LLMRefusal),
        ({"content": '{"missing":true}'}, "stop", LLMError),
    ],
)
def test_invalid_completions_fail(wire, message, reason, error):
    _, replies = wire
    replies.append(completion(message, reason))
    with pytest.raises(error):
        select_client().complete_json("s", "q", Verdict)
