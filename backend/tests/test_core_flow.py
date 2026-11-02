"""Çekirdek akış (#21): sahiplik, onay (consent), kanıt kaydı — sor/pratik/değerlendir/video.

Gerçek veritabanı, LLM'siz /ask (alıntı modu) ve pratik için sahte modeller (test_practice).
Eğitmen `client` (conftest); öğrenciler `client_for` ile ayrı oturumlardır.
"""

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Chunk,
    Conversation,
    Course,
    Document,
    Message,
    PracticeAttempt,
    PracticeQuestion,
    User,
)
from app.verification.practice_checks import MCQSolution
from tests.conftest import enroll, make_pdf, make_user, make_vtt
from tests.test_flow import upload
from tests.test_practice import LONG_PAGES, FakeJSON, mcq, use
from tests.test_video import LESSON, upload_vtt


@dataclass
class World:
    course: Course
    pdf: dict
    video: dict
    student_a: User
    student_b: User


@pytest.fixture
def world(client: TestClient, db: Session, course: Course, tmp_path: Path) -> World:
    """Eğitmen PDF + .vtt yükler; A ve B öğrenci olarak kayıtlı (ikisi de onaylı)."""
    pdf = upload(client, course.id, make_pdf(tmp_path / "arama.pdf", LONG_PAGES))
    video = upload_vtt(client, course.id, make_vtt(tmp_path / "ders.vtt", LESSON))
    assert pdf.status_code == 201 and video.status_code == 201
    a = make_user(db, "ogrenci-a@example.com")
    b = make_user(db, "ogrenci-b@example.com")
    enroll(db, a, course, "student")
    enroll(db, b, course, "student")
    return World(course, pdf.json(), video.json(), a, b)


def ask(c: TestClient, course: Course, question="ikili arama hedef dizi", **extra):
    return c.post("/ask", json={"course_id": course.id, "question": question, **extra})


def approved_chunk_ids(db: Session, course: Course) -> set[str]:
    rows = db.scalars(
        select(Chunk.id)
        .join(Document)
        .where(
            Document.course_id == course.id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
        )
    )
    return {str(r) for r in rows}


def test_ask_with_and_without_video_persists_owned_evidence(
    client_for, db: Session, world: World
) -> None:
    """Soru (videolu / videosuz) onaylı dokümanlara alıntı yapar; sohbet A'ya ait kaydedilir."""
    student = client_for(world.student_a)
    video_ref = {"document_id": world.video["id"], "time_s": 100}

    plain = ask(student, world.course)
    with_video = ask(student, world.course, video=video_ref)

    allowed = approved_chunk_ids(db, world.course)
    for response in (plain, with_video):
        body = response.json()
        assert response.status_code == 200, response.text
        assert body["mode"] == "extractive" and body["declined"] is False
        assert body["citations"] and {c["source_id"] for c in body["citations"]} <= allowed
        assert {h["source_id"] for h in body["retrieval"]} <= allowed
        conversation = db.get(Conversation, body["conversation_id"])
        assert (conversation.user_id, conversation.course_id) == (
            world.student_a.id,
            world.course.id,
        )
        messages = db.scalars(
            select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id)
        ).all()
        assert [m.role for m in messages] == ["user", "assistant"]
        assert messages[0].content == "ikili arama hedef dizi"
        cited = {c["source_id"] for c in body["citations"]}
        assert set(messages[1].meta["cited_source_ids"]) == cited
        assert messages[1].meta["outcome"] == "answered" and messages[1].meta["declined"] is False
    assert plain.json()["conversation_id"] != with_video.json()["conversation_id"]


def test_practice_attempt_is_stored_for_the_student_with_evidence(
    client: TestClient, client_for, db: Session, world: World, monkeypatch
) -> None:
    """Pratik: soru kaynak parçaya ve rubriğe bağlı; deneme A adına, geri bildirim kaynaklı."""
    chunk_id = str(client.get(f"/documents/{world.pdf['id']}/chunks").json()[0]["id"])
    checker = FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S"))
    use(monkeypatch, FakeJSON("gen", mcq()), checker)
    student = client_for(world.student_a)

    item = student.post(
        "/practice", json={"course_id": world.course.id, "type": "mcq", "source_id": chunk_id}
    )
    answer = student.post(f"/practice/{item.json()['id']}/answer", json={"selected_option": 0})

    assert item.status_code == 200, item.text
    assert answer.status_code == 200, answer.text
    feedback = answer.json()
    assert feedback["score"] == 1 and feedback["citations"][0]["source_id"] == chunk_id
    question = db.get(PracticeQuestion, item.json()["id"])
    assert question.requested_by == world.student_a.id and question.course_id == world.course.id
    assert question.rubric.source_ids == [chunk_id] and question.chunk_id == int(chunk_id)
    attempt = db.get(PracticeAttempt, feedback["attempt_id"])
    assert (attempt.user_id, attempt.question_id) == (world.student_a.id, question.id)
    assert attempt.selected_option == 0 and (attempt.score, attempt.max_score) == (1, 1)
    assert attempt.feedback["understood"] == ["ikili arama adımı"]

    # B, A'nın pratik sorusuna cevap verirse kendi adına kaydedilir; A'nın denemesi değişmez.
    other = client_for(world.student_b).post(
        f"/practice/{item.json()['id']}/answer", json={"selected_option": 2}
    )
    users = db.scalars(select(PracticeAttempt.user_id).order_by(PracticeAttempt.id)).all()
    assert other.status_code == 200 and users == [world.student_a.id, world.student_b.id]
    # B, A'nın denemesinden takip sorusu isteyemez (sahiplik): 404.
    follow_up = client_for(world.student_b).post(
        "/practice",
        json={
            "course_id": world.course.id,
            "type": "mcq",
            "follow_up_of_attempt_id": attempt.id,
        },
    )
    assert follow_up.status_code == 404
    assert follow_up.json()["code"] == "practice_item_not_found"


def test_other_student_cannot_read_or_continue_a_conversation(
    client_for, db: Session, world: World
) -> None:
    """B, A'nın sohbetine ne /ask ne /tutor ile devam edebilir (404); A'nın mesajları değişmez."""
    conversation_id = ask(client_for(world.student_a), world.course).json()["conversation_id"]
    student_b = client_for(world.student_b)

    via_ask = ask(student_b, world.course, conversation_id=conversation_id)
    via_tutor = student_b.post(
        "/tutor/turn",
        json={"course_id": world.course.id, "message": "devam", "conversation_id": conversation_id},
    )
    via_stream = ask_stream_status(student_b, world.course, conversation_id)

    for response in (via_ask, via_tutor):
        assert response.status_code == 404
        assert response.json()["code"] == "conversation_not_found"
    assert via_stream == 404
    stored = db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all()
    assert len(stored) == 2


def ask_stream_status(c: TestClient, course: Course, conversation_id: int) -> int:
    body = {"course_id": course.id, "question": "?", "conversation_id": conversation_id}
    return c.post("/ask/stream", json=body).status_code


def test_non_member_is_refused_everywhere(
    client: TestClient, client_for, db: Session, world: World, monkeypatch
) -> None:
    """Derse kayıtlı olmayan (onaylı) kullanıcı: ders, materyal, kaynak, dosya, pratik → 404."""
    outsider = client_for(make_user(db, "disaridan@example.com"))
    chunk_id = str(client.get(f"/documents/{world.pdf['id']}/chunks").json()[0]["id"])
    course_id = world.course.id
    use(
        monkeypatch,
        FakeJSON("gen", mcq()),
        FakeJSON("checker", MCQSolution(answerable=True, chosen_option=0, reason="S")),
    )
    item = client.post(
        "/practice", json={"course_id": course_id, "type": "mcq", "source_id": chunk_id}
    )
    assert item.status_code == 200, item.text

    responses = [
        ask(outsider, world.course),
        outsider.get(f"/courses/{course_id}/materials"),
        outsider.get(f"/documents/{world.pdf['id']}/file"),
        outsider.get(f"/documents/{world.pdf['id']}/chunks"),
        outsider.get(f"/sources/{chunk_id}"),
        outsider.post("/practice", json={"course_id": course_id, "type": "mcq"}),
        outsider.post(f"/practice/{item.json()['id']}/answer", json={"selected_option": 0}),
        outsider.post("/tutor/turn", json={"course_id": course_id, "message": "merhaba"}),
    ]

    assert [r.status_code for r in responses] == [404] * len(responses)
    assert db.scalars(select(PracticeAttempt)).all() == []


def test_student_without_consent_is_refused_on_ask_tutor_and_practice(
    client: TestClient, client_for, db: Session, world: World
) -> None:
    """Onaysız öğrenci: soru, tutor ve pratik 403 consent_required; hiçbir kayıt oluşmaz."""
    pending = make_user(db, "onaysiz@example.com", consented=False)
    enroll(db, pending, world.course, "student")
    student = client_for(pending)
    chunk_id = str(client.get(f"/documents/{world.pdf['id']}/chunks").json()[0]["id"])
    course_id = world.course.id
    question = PracticeQuestion(
        course_id=course_id,
        chunk_id=int(chunk_id),
        requested_by=None,
        type="mcq",
        difficulty="medium",
        prompt="Soru?",
        options=["a", "b"],
        answer_key={"correct_option": 0},
        explanation="x",
        status="released",
        checks=[],
    )
    db.add(question)
    db.commit()

    responses = [
        ask(student, world.course),
        student.post("/ask/stream", json={"course_id": course_id, "question": "?"}),
        student.post("/tutor/turn", json={"course_id": course_id, "message": "merhaba"}),
        student.post("/practice", json={"course_id": course_id, "type": "mcq"}),
        student.post(f"/practice/{question.id}/answer", json={"selected_option": 0}),
    ]

    for response in responses:
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "consent_required"
    assert db.scalars(select(Conversation)).all() == []
    assert db.scalars(select(PracticeAttempt)).all() == []
    # Okuma yolları onay istemez: materyal listesi yine de açılır.
    assert student.get(f"/courses/{course_id}/materials").status_code == 200


def test_unapproved_or_unready_documents_never_reach_students(
    client: TestClient, client_for, db: Session, world: World, tmp_path: Path
) -> None:
    """Onaysız ya da hazır olmayan doküman öğrenciye listede, aramada, alıntıda, dosyada yok."""
    secret = [("Gizli Konu", "Kuantum dolanikligi zeptosaniye olceginde izlenir, kuantum kuantum.")]
    ids = {}
    for name, change in (
        ("onaysiz", {"approved_at": None}),
        ("isleniyor", {"status": "processing"}),
    ):
        document = upload(
            client, world.course.id, make_pdf(tmp_path / f"{name}.pdf", secret)
        ).json()
        db.query(Document).filter(Document.id == document["id"]).update(change)
        ids[name] = document["id"]
    db.commit()
    hidden_chunks = {
        str(c) for c in db.scalars(select(Chunk.id).where(Chunk.document_id.in_(ids.values())))
    }
    assert hidden_chunks
    student = client_for(world.student_a)

    body = ask(student, world.course, "kuantum dolanikligi zeptosaniye").json()
    listed = {d["id"] for d in student.get(f"/courses/{world.course.id}/materials").json()}
    instructor_listed = {
        d["id"] for d in client.get(f"/courses/{world.course.id}/materials").json()
    }

    seen = {c["source_id"] for c in body["citations"]} | {h["source_id"] for h in body["retrieval"]}
    assert not seen & hidden_chunks
    assert body["declined"] is True and body["citations"] == []
    assert listed == {world.pdf["id"], world.video["id"]}
    assert set(ids.values()) <= instructor_listed  # eğitmen hepsini görür
    for document_id in ids.values():
        assert student.get(f"/documents/{document_id}/file").status_code == 404
        assert student.get(f"/documents/{document_id}/chunks").status_code == 404
    for chunk_id in hidden_chunks:
        assert student.get(f"/sources/{chunk_id}").status_code == 404
        assert client.get(f"/sources/{chunk_id}").status_code == 200
