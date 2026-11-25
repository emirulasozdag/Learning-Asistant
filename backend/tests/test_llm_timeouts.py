import asyncio
import time
from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api import tutor as tutor_api
from app.core.config import Settings, settings
from app.llm import chat_completions, deadline
from app.llm.base import LLMError
from app.llm.chat_completions import ChatCompletionsClient
from app.llm.deadline import (
    DEADLINE_ERROR_DETAIL,
    TutorTurnDeadlineExceeded,
    request_timed_out_at_deadline,
    request_timeout,
    tutor_turn_deadline,
)
from app.llm.gateway import select_client
from app.llm.routing import DataClass
from app.schemas.tutor import TutorTurnRequest
from app.tutor import orchestrator as tutor_orchestrator
from app.tutor import service as tutor_service


@pytest.mark.parametrize(
    ("provider", "data"),
    [
        ("gemini", DataClass.COURSE_EVIDENCE),
        ("openai", DataClass.COURSE_EVIDENCE),
        ("anthropic", DataClass.COURSE_EVIDENCE),
        ("openrouter", DataClass.COURSE_EVIDENCE),
        ("local", DataClass.PERSONAL),
    ],
)
def test_llm_timeout_setting_reaches_every_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str, data: DataClass
) -> None:
    timeout_s = 12.5
    monkeypatch.setattr(settings, "llm_timeout_s", timeout_s)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_model", "test-model")

    if provider == "local":
        monkeypatch.setattr(settings, "llm_student_work_route", "local")
        monkeypatch.setattr(settings, "llm_local_base_url", "http://localhost:11434/v1")
        monkeypatch.setattr(settings, "llm_local_model", "test-model")
    else:
        monkeypatch.setattr(settings, "llm_provider", provider)

    client = select_client(data=data)
    assert client is not None

    if provider == "gemini":
        actual_timeout_s = client._client._api_client._http_options.timeout / 1000
    elif provider == "local":
        timeout = client._client._client.timeout
        actual_timeout_s = getattr(timeout, "read", timeout)
    else:
        timeout = client._client.timeout
        actual_timeout_s = getattr(timeout, "read", timeout)

    assert actual_timeout_s == timeout_s


@pytest.mark.parametrize("setting", ["llm_timeout_s", "tutor_turn_deadline_s"])
def test_timeout_settings_must_be_finite_and_positive(setting: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{setting: 0})
    with pytest.raises(ValidationError):
        Settings(**{setting: float("inf")})


def test_provider_timeout_is_capped_by_the_remaining_turn_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(deadline, "monotonic", lambda: now)

    with tutor_turn_deadline(2.0):
        assert request_timeout(90.0) == (2.0, True)
        now = 101.5
        assert request_timeout(90.0) == (0.5, True)
        now = 102.0
        with pytest.raises(TutorTurnDeadlineExceeded):
            request_timeout(90.0)

    with tutor_turn_deadline(30.0):
        assert request_timeout(12.5) == (12.5, True)


def test_provider_timeout_is_a_deadline_only_when_the_budget_is_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(deadline, "monotonic", lambda: now)

    with tutor_turn_deadline(2.0):
        started_at = now
        now = 100.1
        assert not request_timed_out_at_deadline(90.0, started_at)
        now = 101.99
        assert request_timed_out_at_deadline(90.0, started_at)
        now = 102.1
        assert request_timed_out_at_deadline(90.0, started_at)

    with tutor_turn_deadline(30.0):
        started_at = now
        now += 12.5
        assert not request_timed_out_at_deadline(12.5, started_at)


def test_early_chat_completions_timeout_remains_a_provider_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    monkeypatch.setattr(deadline, "monotonic", lambda: now)
    monkeypatch.setattr(chat_completions, "monotonic", lambda: now)
    client = ChatCompletionsClient(
        name="openrouter",
        api_key="test-key",
        model="test-model",
        base_url="https://example.test/v1",
        timeout_s=90.0,
    )

    class Completions:
        def create(self, **kwargs: object) -> None:
            nonlocal now
            now = 100.1
            raise openai.APITimeoutError(request=httpx.Request("POST", "https://example.test"))

    request_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(client, "_request_client", lambda: request_client)

    with tutor_turn_deadline(2.0):
        with pytest.raises(LLMError) as error:
            list(client.stream_text("system", []))

    assert not isinstance(error.value, TutorTurnDeadlineExceeded)


def test_tutor_deadline_is_not_treated_as_a_recoverable_llm_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def deadline_error(ctx, client):
        if False:
            yield None
        raise TutorTurnDeadlineExceeded

    monkeypatch.setattr(tutor_orchestrator, "_orchestrated", deadline_error)

    with pytest.raises(TutorTurnDeadlineExceeded):
        next(
            tutor_orchestrator.run_turn(
                SimpleNamespace(video=None, message="hello"), SimpleNamespace(model="fake")
            )
        )


def test_tutor_deadline_rolls_back_before_persisting_turn_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    db = FakeSession()
    course = SimpleNamespace(id=1, name="Test course", language="en")
    request = TutorTurnRequest(course_id=1, message="hello")
    cleanup: list[int] = []
    monkeypatch.setattr(settings, "tutor_turn_deadline_s", 0.01)
    monkeypatch.setattr(tutor_service, "get_conversation", lambda *args: SimpleNamespace(id=7))
    monkeypatch.setattr(tutor_service, "conversation_history", lambda *args: [])
    monkeypatch.setattr(tutor_service, "_recent_sources", lambda *args: [])
    monkeypatch.setattr(
        tutor_service,
        "_discard_empty",
        lambda session, conversation_id: cleanup.append(conversation_id),
    )

    def slow_turn(ctx, client):
        time.sleep(0.02)
        from app.llm.deadline import check_tutor_turn_deadline

        check_tutor_turn_deadline()
        yield None

    monkeypatch.setattr(tutor_service, "run_turn", slow_turn)

    with pytest.raises(TutorTurnDeadlineExceeded):
        next(tutor_service.turn_stream(db, course, request, None, None))

    assert db.commits == 1
    assert db.rollbacks == 1
    assert cleanup == [7]


def test_tutor_deadline_preserves_existing_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.commits = 0
            self.rollbacks = 0

        def commit(self) -> None:
            self.commits += 1

        def rollback(self) -> None:
            self.rollbacks += 1

    db = FakeSession()
    course = SimpleNamespace(id=1, name="Test course", language="en")
    conversation = SimpleNamespace(id=7, messages=["existing message"])
    request = TutorTurnRequest(course_id=1, conversation_id=7, message="hello")
    cleanup: list[int] = []
    monkeypatch.setattr(settings, "tutor_turn_deadline_s", 0.01)
    monkeypatch.setattr(tutor_service, "get_conversation", lambda *args: conversation)
    monkeypatch.setattr(tutor_service, "conversation_history", lambda *args: [])
    monkeypatch.setattr(tutor_service, "_recent_sources", lambda *args: [])
    monkeypatch.setattr(
        tutor_service,
        "_discard_empty",
        lambda session, conversation_id: cleanup.append(conversation_id),
    )

    def slow_turn(ctx, client):
        time.sleep(0.02)
        deadline.check_tutor_turn_deadline()
        yield None

    monkeypatch.setattr(tutor_service, "run_turn", slow_turn)

    with pytest.raises(TutorTurnDeadlineExceeded):
        next(tutor_service.turn_stream(db, course, request, None, None))

    assert db.rollbacks == 1
    assert conversation.messages == ["existing message"]
    assert cleanup == []


def test_sync_tutor_deadline_maps_to_gateway_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    request = TutorTurnRequest(course_id=1, message="hello")
    user = SimpleNamespace(id=1, user=SimpleNamespace())
    course = SimpleNamespace(id=1)
    monkeypatch.setattr(tutor_api, "_course_for_turn", lambda *args: course)
    monkeypatch.setattr(tutor_api, "checked_video", lambda *args: None)
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: None)
    monkeypatch.setattr(tutor_api, "select_client", lambda *args: None)

    def deadline_error(*args, **kwargs):
        raise TutorTurnDeadlineExceeded

    monkeypatch.setattr(tutor_api.service, "turn", deadline_error)

    with pytest.raises(HTTPException) as error:
        tutor_api.turn(request, user, SimpleNamespace())

    assert error.value.status_code == 504
    assert error.value.detail == DEADLINE_ERROR_DETAIL


def test_streaming_tutor_deadline_maps_to_retryable_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = TutorTurnRequest(course_id=1, message="hello")
    user = SimpleNamespace(id=1, user=SimpleNamespace())
    course = SimpleNamespace(id=1)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, model, record_id):
            return course if model is tutor_api.Course else user.user

    @contextmanager
    def sessions():
        yield FakeSession()

    def deadline_stream(*args, **kwargs):
        if False:
            yield None
        raise TutorTurnDeadlineExceeded

    monkeypatch.setattr(tutor_api, "_course_for_turn", lambda *args: course)
    monkeypatch.setattr(tutor_api, "checked_video", lambda *args: None)
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: None)
    monkeypatch.setattr(tutor_api, "select_client", lambda *args: None)
    monkeypatch.setattr(tutor_api.service, "turn_stream", deadline_stream)
    response = tutor_api.turn_stream(request, user, SimpleNamespace(), sessions)

    async def read_response() -> str:
        chunks = [chunk async for chunk in response.body_iterator]
        return "".join(chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks)

    body = asyncio.run(read_response())

    assert "event: error" in body
    assert DEADLINE_ERROR_DETAIL in body
