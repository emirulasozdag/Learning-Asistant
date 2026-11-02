"""#88: AI Tutor model çağrıları açık bir veritabanı işlemi içinde beklemez (gerçek veritabanı).

Sahte orkestratör ve üretici her çağrıda `pg_stat_activity`'ye bakar: turu yürüten oturumun
bağlantısı "idle in transaction" olmamalı.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db.models import Conversation, Course, Message
from app.llm.base import LLMError
from tests.test_answer import FakeLLM
from tests.test_flow import upload
from tests.test_tutor import ANSWER, FakeOrchestrator, call, turn, use

OPEN_TRANSACTIONS = text(
    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
    "AND pid <> pg_backend_pid() AND state LIKE 'idle in transaction%'"
)


@pytest.fixture
def ready(client: TestClient, course: Course, sample_pdf: Path) -> None:
    upload(client, course.id, sample_pdf)


def open_transactions(db_engine) -> int:
    with db_engine.connect() as connection:
        return connection.scalar(OPEN_TRANSACTIONS)


class ProbingLLM(FakeLLM):
    def __init__(self, db_engine, chunks: list[str]) -> None:
        super().__init__(chunks)
        self.db_engine = db_engine
        self.seen: list[int] = []

    def stream_text(self, system, messages):
        self.seen.append(open_transactions(self.db_engine))
        yield from super().stream_text(system, messages)


class ProbingOrchestrator(FakeOrchestrator):
    def __init__(self, db_engine, *steps) -> None:
        super().__init__(*steps)
        self.db_engine = db_engine
        self.seen: list[int] = []

    def tool_conversation(self, system, messages, tools):
        conversation = super().tool_conversation(system, messages, tools)
        step = conversation.step

        def probing_step():
            self.seen.append(open_transactions(self.db_engine))
            return step()

        conversation.step = probing_step
        return conversation


@pytest.mark.parametrize("existing", [False, True])
def test_model_calls_run_with_no_open_transaction(
    client: TestClient,
    db: Session,
    db_engine,
    course: Course,
    ready,
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    extra = {}
    if existing:
        use(monkeypatch, None, FakeLLM([ANSWER]))
        extra["conversation_id"] = turn(client, course, "Neden sag yari elenir?")["conversation_id"]
    orchestrator = ProbingOrchestrator(
        db_engine,
        [call("answer_from_course", question="Neden sag yari elenir?")],
        [call("finish")],
    )
    generator = ProbingLLM(db_engine, [ANSWER])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "peki neden?", **extra)

    assert orchestrator.seen == [0, 0]
    assert generator.seen == [0]
    assert body["blocks"][0]["response"]["conversation_id"] == body["conversation_id"]
    messages = db.scalars(
        select(Message).where(Message.conversation_id == body["conversation_id"])
    ).all()
    assert [m.role for m in messages][-2:] == ["user", "assistant"]


def test_conversation_deleted_during_the_turn_is_not_found(
    client: TestClient,
    db: Session,
    db_engine,
    course: Course,
    ready,
    monkeypatch,
) -> None:
    use(monkeypatch, None, FakeLLM([ANSWER]))
    conversation_id = turn(client, course, "Neden sag yari elenir?")["conversation_id"]

    class DeletesConversation(FakeLLM):
        def stream_text(self, system, messages):
            with Session(db_engine) as other:
                other.delete(other.get(Conversation, conversation_id))
                other.commit()
            yield from super().stream_text(system, messages)

    use(monkeypatch, None, DeletesConversation([ANSWER]))
    response = client.post(
        "/tutor/turn",
        json={
            "course_id": course.id,
            "message": "Neden sag yari elenir?",
            "conversation_id": conversation_id,
        },
    )

    assert response.status_code == 404 and response.json()["code"] == "conversation_not_found"
    db.expire_all()
    assert db.scalar(select(func.count(Message.id))) == 0


def test_failed_turn_leaves_no_empty_new_conversation(
    client: TestClient,
    db: Session,
    course: Course,
    ready,
    monkeypatch,
) -> None:
    class Breaks(FakeOrchestrator):
        def tool_conversation(self, system, messages, tools):
            raise RuntimeError("beklenmeyen")

    use(monkeypatch, Breaks(), FakeLLM([ANSWER]))

    with pytest.raises(RuntimeError, match="beklenmeyen"):
        client.post("/tutor/turn", json={"course_id": course.id, "message": "Neden?"})

    db.expire_all()
    assert db.scalar(select(func.count(Conversation.id))) == 0


def test_ask_conversation_deleted_during_generation_is_not_found(
    client: TestClient,
    db: Session,
    db_engine,
    course: Course,
    ready,
    monkeypatch,
) -> None:
    """Aynı denetim `/ask` için (#21'de sohbet tur sonunda yeniden okunuyor)."""
    from app.api import ask as ask_api

    monkeypatch.setattr(ask_api, "select_client", lambda: FakeLLM([ANSWER]))
    first = client.post("/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"})
    conversation_id = first.json()["conversation_id"]

    class DeletesConversation(FakeLLM):
        def stream_text(self, system, messages):
            with Session(db_engine) as other:
                other.delete(other.get(Conversation, conversation_id))
                other.commit()
            yield from super().stream_text(system, messages)

    monkeypatch.setattr(ask_api, "select_client", lambda: DeletesConversation([ANSWER]))
    response = client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": "Neden sag yari elenir?",
            "conversation_id": conversation_id,
        },
    )

    assert response.status_code == 404 and response.json()["code"] == "conversation_not_found"


def test_orchestrator_error_still_falls_back_and_saves_the_turn(
    client: TestClient,
    db: Session,
    course: Course,
    ready,
    monkeypatch,
) -> None:
    """Sarmalayıcı LLMError'ı değiştirmez: orkestratör hatasında sabit akış çalışır."""
    use(monkeypatch, FakeOrchestrator(error=LLMError("kapalı")), FakeLLM([ANSWER]))

    body = turn(client, course, "Neden sag yari elenir?")

    assert body["trace"]["fallback_reason"] == "orchestrator_error"
    db.expire_all()
    assert db.scalar(select(func.count(Message.id))) == 2
