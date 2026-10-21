"""AI Tutor turu: orkestratör → araçlar → kökeni etiketli bloklar (gerçek veritabanı).

Orkestratör ve üretici sahtedir: orkestratör önceden yazılmış araç çağrılarını sırayla döndürür.
`client` dersin eğitmeni olarak oturum açmıştır (conftest).
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api import tutor as tutor_api
from app.core.config import settings
from app.db.models import Course, Message
from app.llm.base import ChatMessage, LLMError, LLMUsage, ToolCall, ToolSpec
from app.llm.gateway import LLMRole
from tests.conftest import enroll, make_user
from tests.test_answer import FakeLLM
from tests.test_flow import parse_sse, upload

ANSWER = "Dizi sirali oldugu icin sag yari elenir [S1]."


class FakeConversation:
    def __init__(self, owner: "FakeOrchestrator") -> None:
        self.owner = owner

    def step(self) -> list[ToolCall]:
        if self.owner.error:
            raise self.owner.error
        return self.owner.script.pop(0)

    def add_results(self, results: list[tuple[ToolCall, dict]]) -> None:
        self.owner.results.append(results)


class FakeOrchestrator:
    name = "fake"
    model = "fake-orchestrator"

    def __init__(self, *steps: list[ToolCall], error: Exception | None = None) -> None:
        self.script = list(steps)
        self.error = error
        self.usage: list[LLMUsage] = [
            LLMUsage("gemini-3.5-flash-lite", "orchestrator", 1000, 50, cached_tokens=800)
        ]
        self.results: list[list[tuple[ToolCall, dict]]] = []
        self.system = ""
        self.messages: list[ChatMessage] = []
        self.tools: list[str] = []

    def tool_conversation(
        self, system: str, messages: list[ChatMessage], tools: list[ToolSpec]
    ) -> FakeConversation:
        self.system, self.messages, self.tools = system, messages, [t.name for t in tools]
        return FakeConversation(self)

    def result(self, step: int, index: int = 0) -> dict:
        return self.results[step][index][1]


def call(name: str, **args) -> ToolCall:
    return ToolCall(name, args, f"{name}-id")


@pytest.fixture
def ready(client: TestClient, course: Course, sample_pdf: Path) -> None:
    upload(client, course.id, sample_pdf)


def use(
    monkeypatch: pytest.MonkeyPatch,
    orchestrator: FakeOrchestrator | None,
    generator: FakeLLM | None,
) -> None:
    monkeypatch.setattr(tutor_api, "select_orchestrator", lambda: orchestrator)
    # Yalnızca üretici sahte; kontrolcü ve yeniden sıralayıcı yok (gerekirse testte verilir).
    monkeypatch.setattr(
        tutor_api,
        "select_client",
        lambda role=LLMRole.GENERATOR: generator if role is LLMRole.GENERATOR else None,
    )


def turn(client: TestClient, course: Course, message: str, **extra) -> dict:
    response = client.post(
        "/tutor/turn", json={"course_id": course.id, "message": message, **extra}
    )
    assert response.status_code == 200, response.text
    return response.json()


def kinds(body: dict) -> list[str]:
    return [block["type"] for block in body["blocks"]]


def test_without_orchestrator_the_turn_uses_the_direct_course_answer(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, None, FakeLLM([ANSWER]))

    body = turn(client, course, "Neden sag yari elenir?")

    assert kinds(body) == ["course_answer", "follow_ups"]
    answer = body["blocks"][0]
    assert answer["provenance"] == "course"
    assert answer["response"]["answer"] == "Dizi sirali oldugu icin sag yari elenir [1]."
    assert body["trace"]["mode"] == "direct"
    assert body["trace"]["fallback_reason"] == "no_orchestrator"
    assert [s["tool"] for s in body["trace"]["steps"]] == ["answer_from_course", "finish"]


def test_orchestrator_completes_the_question_and_only_sees_a_status(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = FakeOrchestrator(
        [call("answer_from_course", question="Neden sag yari elenir?")],
        [call("finish", follow_ups=["example"])],
    )
    generator = FakeLLM([ANSWER])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "peki neden?")

    _, messages = generator.calls[0]
    assert messages[-1]["content"].endswith("Soru: Neden sag yari elenir?")
    assert kinds(body) == ["course_answer", "follow_ups"]
    assert body["blocks"][1]["items"][0]["action"] == "example"
    # Orkestratöre öğretim içeriği değil, yalnızca durum döner.
    result = orchestrator.result(0)
    assert result == {"status": "answered", "citations": 1, "sources": ["notlar"]}
    assert "peki neden?" in orchestrator.messages[-1]["content"]
    assert body["trace"]["mode"] == "orchestrated"
    assert body["trace"]["orchestrator_model"] == "fake-orchestrator"
    assert body["trace"]["usage"][0]["cost_usd"] == pytest.approx(
        (200 * 0.30 + 800 * 0.03 + 50 * 2.50) / 1_000_000
    )


def test_orchestrator_failure_falls_back_to_the_direct_flow(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, FakeOrchestrator(error=LLMError("kota")), FakeLLM([ANSWER]))

    body = turn(client, course, "Neden sag yari elenir?")

    assert kinds(body) == ["course_answer", "follow_ups"]
    assert body["trace"]["mode"] == "direct"
    assert body["trace"]["fallback_reason"] == "orchestrator_error"


def test_finishing_without_any_content_falls_back_to_the_direct_flow(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, FakeOrchestrator([call("finish")]), FakeLLM([ANSWER]))

    body = turn(client, course, "Neden sag yari elenir?")

    assert kinds(body)[0] == "course_answer"
    assert body["trace"]["fallback_reason"] == "no_content"


def test_greeting_is_a_fixed_notice_and_is_not_counted_as_a_question(
    client: TestClient, db, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    generator = FakeLLM(["olmamali"])
    use(monkeypatch, FakeOrchestrator([call("reply_notice", kind="greeting")]), generator)

    body = turn(client, course, "Merhaba!")

    assert kinds(body) == ["notice"]
    assert body["blocks"][0]["kind"] == "greeting"
    assert course.name in body["blocks"][0]["text"]
    assert generator.calls == []
    stored = db.scalars(select(Message).where(Message.role == "assistant")).one()
    assert stored.meta["counted"] is False and stored.meta["tutor"] is True


def test_invalid_arguments_go_back_to_the_model_as_a_rejection(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = FakeOrchestrator(
        [call("answer_from_course")],
        [call("answer_from_course", question="Neden sag yari elenir?")],
        [call("finish")],
    )
    use(monkeypatch, orchestrator, FakeLLM([ANSWER]))

    body = turn(client, course, "Neden sag yari elenir?")

    assert orchestrator.result(0)["status"] == "rejected"
    assert "Geçersiz argüman" in orchestrator.result(0)["reason"]
    assert orchestrator.result(1)["status"] == "answered"
    assert [s["status"] for s in body["trace"]["steps"]] == ["invalid", "answered", "finished"]


def test_general_knowledge_is_off_by_default(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = FakeOrchestrator(
        [call("answer_from_course", question="Hash tablosu nedir?")],
        [call("explain_general", question="Hash tablosu nedir?")],
        [call("finish")],
    )
    generator = FakeLLM(["olmamali"])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "Hash tablosu nedir?")

    assert "explain_general" not in orchestrator.tools
    assert orchestrator.result(0) == {
        "status": "not_covered",
        "general_explanation_available": False,
    }
    assert orchestrator.result(1)["status"] == "rejected"  # tanımlı olmayan araç
    assert kinds(body) == ["course_answer"]
    assert body["blocks"][0]["response"]["outcome"] == "insufficient_evidence"
    assert generator.calls == []


def test_not_covered_question_gets_a_labelled_general_explanation_when_enabled(
    client: TestClient, db, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "tutor_general_knowledge", True)
    orchestrator = FakeOrchestrator(
        [call("answer_from_course", question="Hash tablosu nedir?")],
        [call("explain_general", question="Hash tablosu nedir?")],
        [call("finish")],
    )
    generator = FakeLLM(["Hash tablosu anahtarlari ", "bir dizide saklar."])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "Hash tablosu nedir?")

    assert kinds(body) == ["course_answer", "general_explanation"]
    general = body["blocks"][1]
    assert general["provenance"] == "general" and general["check"] == "unchecked"
    assert general["text"] == "Hash tablosu anahtarlari bir dizide saklar."
    assert "ders materyalinden değil" in general["notice"]
    assert "[S" not in generator.calls[0][1][-1]["content"].split("Soru:")[-1]
    stored = db.scalars(select(Message).where(Message.role == "assistant")).one()
    assert stored.meta["outcome"] == "insufficient_evidence"  # eğitmene materyal boşluğu
    assert "(Genel bilgi, ders materyalinden değil)" in stored.content


def test_general_explanation_needs_a_not_covered_answer_first(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "tutor_general_knowledge", True)
    orchestrator = FakeOrchestrator(
        [call("explain_general", question="Neden sag yari elenir?")],
        [call("answer_from_course", question="Neden sag yari elenir?")],
        [call("finish")],
    )
    generator = FakeLLM([ANSWER])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "Neden sag yari elenir?")

    assert orchestrator.result(0)["status"] == "rejected"
    assert kinds(body) == ["course_answer"]
    assert len(generator.calls) == 1  # yalnızca kaynaklı cevap


def test_clarification_ends_the_turn(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = FakeOrchestrator(
        [
            call("ask_clarification", question="Hangi konu?", options=["Ikili arama", "BST"]),
            call("answer_from_course", question="olmamali"),
        ]
    )
    generator = FakeLLM(["olmamali"])
    use(monkeypatch, orchestrator, generator)

    body = turn(client, course, "bunu anlamadim")

    assert kinds(body) == ["clarification"]
    assert body["blocks"][0]["options"] == ["Ikili arama", "BST"]
    assert generator.calls == []


def test_the_next_turn_sees_the_previous_turn(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, None, FakeLLM([ANSWER]))
    first = turn(client, course, "Neden sag yari elenir?")
    orchestrator = FakeOrchestrator([call("reply_notice", kind="greeting")])
    use(monkeypatch, orchestrator, FakeLLM([]))

    second = turn(client, course, "tesekkurler", conversation_id=first["conversation_id"])

    assert second["conversation_id"] == first["conversation_id"]
    assert [m["role"] for m in orchestrator.messages] == ["user", "assistant", "user"]
    assert orchestrator.messages[1]["content"] == "Dizi sirali oldugu icin sag yari elenir."


def test_stream_sends_status_drafts_and_verified_blocks(
    client: TestClient, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    orchestrator = FakeOrchestrator(
        [call("answer_from_course", question="Neden sag yari elenir?")], [call("finish")]
    )
    use(monkeypatch, orchestrator, FakeLLM(["Dizi sirali oldugu icin ", "sag yari elenir [S1]."]))

    response = client.post(
        "/tutor/turn/stream", json={"course_id": course.id, "message": "Neden sag yari elenir?"}
    )
    events = parse_sse(response.text)

    names = [name for name, _ in events]
    assert names == ["status", "retrieval", "delta", "delta", "block", "status", "done"]
    assert events[2][1] == {"block_index": 0, "text": "Dizi sirali oldugu icin "}
    block = events[4][1]
    assert block["index"] == 0 and block["block"]["type"] == "course_answer"
    assert events[-1][1]["blocks"][0] == block["block"]


def test_turn_requires_membership_consent_and_own_conversation(
    client: TestClient, client_for, db, course: Course, ready, monkeypatch: pytest.MonkeyPatch
) -> None:
    use(monkeypatch, None, FakeLLM([ANSWER]))
    mine = turn(client, course, "Neden sag yari elenir?")
    unconsented = make_user(db, "onaysiz@example.com", consented=False)
    student = make_user(db, "ogrenci@example.com")
    enroll(db, unconsented, course, "student")
    enroll(db, student, course, "student")
    payload = {"course_id": course.id, "message": "Neden?"}

    outsider = client_for(make_user(db, "disaridan@example.com")).post("/tutor/turn", json=payload)
    no_consent = client_for(unconsented).post("/tutor/turn", json=payload)
    foreign = client_for(student).post(
        "/tutor/turn", json={**payload, "conversation_id": mine["conversation_id"]}
    )

    assert outsider.status_code == 404
    assert no_consent.status_code == 403 and no_consent.json()["code"] == "consent_required"
    assert foreign.status_code == 404 and foreign.json()["code"] == "conversation_not_found"
