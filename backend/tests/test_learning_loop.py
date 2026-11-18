"""Öğrenme kaydı, sık hatalar, eğitmen onayı/düzeltmesi ve rubrik girişi (#20, #15; FR-13, FR-15,
FR-16; ADR-4).

Sorular veritabanına doğrudan yazılır (üretim #16'nın testlerinde); çoktan seçmeli cevaplar
gerçek `/practice/{id}/answer` ucundan geçer (model gerekmez), açık uçlu denemeler değerlendirici
çıktısıyla aynı biçimde saklanır.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.models import (
    Conversation,
    Course,
    Enrollment,
    InstructorReview,
    Message,
    PracticeAttempt,
    PracticeQuestion,
    PracticeRubric,
    PracticeRubricRevision,
    User,
)
from tests.conftest import enroll, make_pdf, make_user
from tests.test_flow import upload

PAGES = [
    (
        "Ikili Arama",
        "Ikili arama sirali bir dizide ortadaki elemanla karsilastirip araligin yarisini atar. "
        "Bu yuzden O(log n) zamanda calisir; dizi sirali degilse dogru sonuc vermez.",
    )
]


@pytest.fixture
def setup(db, client_for, user: User, course: Course, tmp_path: Path) -> SimpleNamespace:
    """Ders (eğitmen `user`), bir parça, araştırma kaydı açık üç öğrenci, kapalı bir öğrenci,
    bir TA ve başka dersin eğitmeni."""
    document = upload(client_for(user), course.id, make_pdf(tmp_path / "arama.pdf", PAGES)).json()
    chunk_id = client_for(user).get(f"/documents/{document['id']}/chunks").json()[0]["id"]
    students = []
    for name in ("ayse", "burak", "cem"):
        student = make_user(db, f"{name}@example.com", research_logging=True)
        enroll(db, student, course, "student")
        students.append(student)
    private = make_user(db, "gizli@example.com", research_logging=False)
    enroll(db, private, course, "student")
    ta = make_user(db, "ta@example.com")
    enroll(db, ta, course, "ta")
    other = make_user(db, "baska@example.com", can_create_courses=True)
    other_course = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other_course)
    db.commit()
    enroll(db, other, other_course, "instructor")
    return SimpleNamespace(
        course=course,
        chunk_id=int(chunk_id),
        students=students,
        private=private,
        ta=ta,
        instructor=user,
        other=other,
    )


def mcq_question(db, s: SimpleNamespace, concept: str, status: str = "released"):
    question = PracticeQuestion(
        course_id=s.course.id,
        chunk_id=s.chunk_id,
        type="mcq",
        topic=concept,
        difficulty="medium",
        prompt=f"{concept} hakkında hangisi doğru?",
        options=["Yarıyı atar", "Baştan tarar", "Diziyi sıralar", "Rastgele seçer"],
        answer_key={"correct_option": 0},
        explanation="Kaynağa göre her adımda aralığın yarısı atılır.",
        status=status,
        checks=[],
    )
    question.rubric = PracticeRubric(
        course_id=s.course.id,
        concept=concept,
        reference_answer="Yarıyı atar.",
        criteria=[{"description": "Doğru şık", "points": 1}],
        source_ids=[str(s.chunk_id)],
        origin="generated",
    )
    db.add(question)
    db.commit()
    return question


def open_attempt(db, s, user: User, concept: str, score: float, missing: list[str]):
    """Açık uçlu soru + değerlendirilmiş deneme (değerlendirici çıktısıyla aynı biçim)."""
    question = mcq_question(db, s, concept)
    question.type, question.options = "short_answer", None
    question.answer_key = {"reference_answer": "Yarıyı attığı için."}
    attempt = PracticeAttempt(
        question_id=question.id,
        user_id=user.id,
        answer_text="cevap",
        score=score,
        max_score=4.0,
        feedback={"understood": [], "missing_concepts": missing, "explanation": "", "criteria": []},
        research_logged=user.research_logging,
    )
    db.add(attempt)
    db.commit()
    return attempt


def answer(client_for, user: User, question: PracticeQuestion, option: int):
    body = {"selected_option": option}
    return client_for(user).post(f"/practice/{question.id}/answer", json=body)


# --- Öğrenme kaydı (FR-15) ---


def test_learning_record_lists_own_logged_attempts_and_concept_progress(
    db, client_for, setup
) -> None:
    s = setup
    ayse, burak = s.students[0], s.students[1]
    search = mcq_question(db, s, "ikili arama adımı")
    assert answer(client_for, ayse, search, 2).status_code == 200  # yanlış
    assert answer(client_for, ayse, search, 0).status_code == 200  # sonra doğru
    open_attempt(db, s, ayse, "ikili arama karmaşıklığı", 2.0, ["log n"])
    assert answer(client_for, burak, search, 1).status_code == 200  # başkasının denemesi

    record = client_for(ayse).get(f"/courses/{s.course.id}/learning-record")

    assert record.status_code == 200, record.text
    body = record.json()
    assert body["logging_enabled"] is True
    assert [a["concept"] for a in body["attempts"]] == [
        "ikili arama karmaşıklığı",
        "ikili arama adımı",
        "ikili arama adımı",
    ]
    assert body["attempts"][0]["missing_concepts"] == ["log n"]
    concepts = {c["concept"]: c for c in body["concepts"]}
    assert concepts["ikili arama adımı"] == {
        "concept": "ikili arama adımı",
        "attempts": 2,
        "last_score_ratio": 1.0,
        "best_score_ratio": 1.0,
        "open_gaps": [],
        "source": concepts["ikili arama adımı"]["source"],
    }
    assert concepts["ikili arama adımı"]["source"]["source_id"] == str(s.chunk_id)
    assert concepts["ikili arama karmaşıklığı"]["open_gaps"] == ["log n"]
    # Eksiği olan kavram önce gelir.
    assert body["concepts"][0]["concept"] == "ikili arama karmaşıklığı"


def test_attempts_made_without_research_logging_stay_out_of_the_record(
    db, client_for, setup
) -> None:
    s = setup
    question = mcq_question(db, s, "ikili arama adımı")
    assert answer(client_for, s.private, question, 1).status_code == 200

    body = client_for(s.private).get(f"/courses/{s.course.id}/learning-record").json()

    assert body == {
        "course_id": s.course.id,
        "logging_enabled": False,
        "attempts": [],
        "concepts": [],
    }
    # Deneme geri bildirim ve takip sorusu için yine de saklanır.
    assert db.scalar(select(PracticeAttempt).where(PracticeAttempt.user_id == s.private.id))


def test_delete_my_data_removes_practice_attempts(db, client_for, setup) -> None:
    s = setup
    ayse = s.students[0]
    answer(client_for, ayse, mcq_question(db, s, "ikili arama adımı"), 1)

    assert client_for(ayse).delete("/me/data").status_code == 204

    assert db.scalars(select(PracticeAttempt).where(PracticeAttempt.user_id == ayse.id)).all() == []
    assert client_for(ayse).get(f"/courses/{s.course.id}/learning-record").json()["attempts"] == []


# --- Sık hatalar (FR-16) ---


def test_frequent_mistakes_are_aggregated_and_small_groups_suppressed(
    db, client_for, setup
) -> None:
    s = setup
    step = mcq_question(db, s, "Ikili arama adımı")
    for student in s.students:
        assert answer(client_for, student, step, 3).status_code == 200
    answer(client_for, s.private, step, 3)  # araştırma kaydı kapalı: sayılmaz
    # Açık uçlu: "log n" eksiği üç öğrencide (yazım farkıyla), "sıralılık" yalnızca ikisinde.
    open_attempt(db, s, s.students[0], "karmaşıklık", 1.0, ["log n", "sıralılık"])
    open_attempt(db, s, s.students[1], "karmaşıklık", 1.0, ["Log  n.", "sıralılık"])
    open_attempt(db, s, s.students[2], "karmaşıklık", 3.0, ["log n"])

    response = client_for(s.instructor).get(f"/instructor/courses/{s.course.id}/mistakes")

    assert response.status_code == 200, response.text
    mistakes = response.json()
    assert [(m["concept"], m["error_type"], m["count"], m["students"]) for m in mistakes] == [
        # Eşit öğrenci ve deneme sayısında kavram adına göre sıralanır.
        ("Ikili arama adımı", "wrong_option", 3, 3),
        ("log n", "missing_concept", 3, 3),
    ]
    assert all(m["fixing_source_ids"] == [str(s.chunk_id)] for m in mistakes)
    assert client_for(s.ta).get(f"/instructor/courses/{s.course.id}/mistakes").status_code == 200


def test_mistakes_disappear_when_a_student_turns_research_logging_off(
    db, client_for, setup
) -> None:
    s = setup
    step = mcq_question(db, s, "ikili arama adımı")
    for student in s.students:
        answer(client_for, student, step, 3)
    s.students[0].research_logging = False
    db.commit()

    response = client_for(s.instructor).get(f"/instructor/courses/{s.course.id}/mistakes")

    assert response.json() == []


def test_students_cannot_see_class_mistakes(client_for, setup) -> None:
    response = client_for(setup.students[0]).get(f"/instructor/courses/{setup.course.id}/mistakes")

    assert response.status_code == 403
    assert response.json()["code"] == "insufficient_role"


# --- Eğitmen onayı / düzeltmesi (FR-16) ---


def review(client, target_type: str, target_id: int, decision: str, correction=None):
    body = {"target_type": target_type, "target_id": target_id, "decision": decision}
    if correction is not None:
        body["correction"] = correction
    return client.post("/instructor/reviews", json=body)


def test_correcting_a_practice_item_withdraws_it_and_approving_restores_it(
    db, client_for, setup
) -> None:
    s = setup
    question = mcq_question(db, s, "ikili arama adımı")
    instructor = client_for(s.instructor)

    corrected = review(instructor, "practice_item", question.id, "correct", "B şıkkı da doğru.")

    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["correction"] == "B şıkkı da doğru."
    db.refresh(question)
    assert question.status == "withdrawn" and question.rubric.approved is False
    blocked = answer(client_for, s.students[0], question, 0)
    assert blocked.status_code == 404 and blocked.json()["code"] == "practice_item_not_found"

    approved = review(instructor, "practice_item", question.id, "approve")

    assert approved.status_code == 200
    db.refresh(question)
    assert question.status == "released"
    assert question.rubric.approved is True and question.rubric.approved_by == s.instructor.id
    decisions = db.scalars(select(InstructorReview.decision).order_by(InstructorReview.id)).all()
    assert decisions == ["correct", "approve"]


def test_correct_decision_requires_a_correction(db, client_for, setup) -> None:
    question = mcq_question(db, setup, "ikili arama adımı")

    response = review(client_for(setup.instructor), "practice_item", question.id, "correct", "  ")

    assert response.status_code == 422


def test_review_permissions_do_not_leak_targets(db, client_for, setup) -> None:
    s = setup
    question = mcq_question(db, s, "ikili arama adımı")
    rejected = mcq_question(db, s, "ikili arama adımı", status="rejected")

    student = review(client_for(s.students[0]), "practice_item", question.id, "approve")
    ta = review(client_for(s.ta), "practice_item", question.id, "approve")
    outsider = review(client_for(s.other), "practice_item", question.id, "approve")
    missing = review(client_for(s.other), "practice_item", 99999, "approve")
    not_released = review(client_for(s.instructor), "practice_item", rejected.id, "approve")

    assert student.status_code == 403 and ta.status_code == 403
    assert outsider.status_code == 404 and outsider.json() == missing.json()
    assert missing.json()["code"] == "practice_item_not_found"
    assert not_released.status_code == 404
    # Veritabanı aralığı dışındaki kimlik 500 değil, 422 (önceden sorguda düşüyordu).
    assert review(client_for(s.instructor), "practice_item", 2**31, "approve").status_code == 422


def conversation_with_answer(db, s, owner: User) -> Message:
    conversation = Conversation(course_id=s.course.id, user_id=owner.id)
    conversation.messages = [
        Message(role="user", content="Ikili arama neden hizli?"),
        Message(
            role="assistant",
            content="Her adimda yarisini atar [1].",
            meta={"outcome": "answered", "cited_source_ids": [str(s.chunk_id)]},
        ),
    ]
    db.add(conversation)
    db.commit()
    return conversation.messages[1]


def test_instructor_reviews_answers_only_from_research_logged_students(
    db, client_for, setup
) -> None:
    s = setup
    logged = conversation_with_answer(db, s, s.students[0])
    private = conversation_with_answer(db, s, s.private)
    instructor = client_for(s.instructor)

    stored = review(instructor, "message", logged.id, "correct", "Sıralı dizi şartını ekle.")
    hidden = review(instructor, "message", private.id, "approve")
    question = review(instructor, "message", logged.id - 1, "approve")  # öğrencinin mesajı

    assert stored.status_code == 200, stored.text
    assert stored.json()["target_id"] == logged.id
    row = db.scalar(select(InstructorReview))
    assert row.message_id == logged.id and row.course_id == s.course.id
    assert hidden.status_code == 404 and hidden.json()["code"] == "message_not_found"
    assert question.status_code == 404


def test_activity_items_carry_the_answer_message_id(db, client_for, setup) -> None:
    s = setup
    answers = [conversation_with_answer(db, s, student) for student in s.students]

    activity = client_for(s.instructor).get(f"/instructor/courses/{s.course.id}/activity").json()

    assert {q["answer_message_id"] for q in activity["recent_questions"]} == {a.id for a in answers}


def test_instructor_lists_practice_items_with_key_and_latest_review(db, client_for, setup) -> None:
    s = setup
    released = mcq_question(db, s, "ikili arama adımı")
    mcq_question(db, s, "ikili arama adımı", status="rejected")  # öğrenciye hiç gitmedi
    instructor = client_for(s.instructor)
    review(instructor, "practice_item", released.id, "correct", "B şıkkı da savunulabilir.")

    response = instructor.get(f"/instructor/courses/{s.course.id}/practice-items")

    assert response.status_code == 200, response.text
    items = response.json()
    assert [item["id"] for item in items] == [released.id]
    item = items[0]
    assert item["status"] == "withdrawn" and item["correct_option"] == 0
    assert item["source"]["source_id"] == str(s.chunk_id)
    assert item["latest_review"]["decision"] == "correct"
    assert item["latest_review"]["correction"] == "B şıkkı da savunulabilir."
    path = f"/instructor/courses/{s.course.id}/practice-items"
    assert client_for(s.ta).get(path).status_code == 200
    assert client_for(s.students[0]).get(path).status_code == 403


# --- Rubrik ve referans cevap girişi (#15) ---


RUBRIC_IN = {
    "concept": "ikili arama",
    "reference_answer": "Sıralı dizide her adımda aralığın yarısı atılır.",
    "criteria": [{"description": "Yarıya inmeyi söyler", "points": 2}],
}


def open_question(db, s, status: str = "released"):
    question = mcq_question(db, s, "ikili arama", status=status)
    question.type, question.options = "short_answer", None
    question.answer_key = {"reference_answer": "Yarıyı attığı için."}
    db.commit()
    return question


def post_rubric(client, s, **changes):
    return client.post(f"/instructor/courses/{s.course.id}/rubrics", json={**RUBRIC_IN, **changes})


def test_instructor_rubric_replaces_and_approves_the_question_rubric(db, client_for, setup) -> None:
    s = setup
    question = open_question(db, s)
    generated_id = question.rubric.id

    response = post_rubric(client_for(s.instructor), s, practice_item_id=question.id)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == generated_id  # aynı satır güncellenir (soru başına tek rubrik)
    assert body["practice_item_id"] == question.id and body["course_id"] == s.course.id
    assert (body["origin"], body["approved"]) == ("instructor", True)
    db.expire_all()
    assert question.rubric.approved_by == s.instructor.id and question.rubric.approved_at
    # Üreticinin anahtarı kanıt olarak kalır; geçerli referans rubriğinki.
    assert question.answer_key == {"reference_answer": "Yarıyı attığı için."}
    assert question.status == "released"  # rubrik girmek soruyu yayımlamaz ya da geri çekmez
    items = client_for(s.instructor).get(f"/instructor/courses/{s.course.id}/practice-items")
    assert items.json()[0]["reference_answer"] == RUBRIC_IN["reference_answer"]
    assert items.json()[0]["rubric_approved"] is True


def test_concept_rubric_is_stored_with_course_sources(db, client_for, setup) -> None:
    s = setup

    # Aynı kaynak iki kez ve başında sıfırla: tekilleştirilir, olağan biçimde saklanır.
    response = post_rubric(
        client_for(s.instructor), s, source_ids=[str(s.chunk_id), f"00{s.chunk_id}"]
    )

    assert response.status_code == 200, response.text
    assert response.json()["practice_item_id"] is None
    assert response.json()["source_ids"] == [str(s.chunk_id)]
    rubric = db.scalar(select(PracticeRubric).where(PracticeRubric.question_id.is_(None)))
    assert rubric.origin == "instructor" and rubric.approved is True


def test_rubric_entry_rejects_invalid_targets(db, client_for, setup) -> None:
    s = setup
    instructor = client_for(s.instructor)
    mcq = mcq_question(db, s, "ikili arama")
    rejected = open_question(db, s, status="rejected")

    choice = post_rubric(instructor, s, practice_item_id=mcq.id)
    hidden = post_rubric(instructor, s, practice_item_id=rejected.id)
    missing = post_rubric(instructor, s, practice_item_id=99999)
    foreign_source = post_rubric(instructor, s, source_ids=["99999"])
    not_a_source = post_rubric(instructor, s, source_ids=["abc"])
    too_many = post_rubric(instructor, s, criteria=[{"description": "x", "points": 1}] * 11)
    zero_points = post_rubric(instructor, s, criteria=[{"description": "x", "points": 0}])
    long_reference = post_rubric(instructor, s, reference_answer="a" * 4001)
    # Veritabanı aralığı dışındaki ve ASCII olmayan kimlikler 500 değil, 422 olur.
    huge_item = post_rubric(instructor, s, practice_item_id=2**31)
    huge_source = post_rubric(instructor, s, source_ids=["9" * 25])
    out_of_range_source = post_rubric(instructor, s, source_ids=[str(2**31)])
    arabic_digits = post_rubric(instructor, s, source_ids=["١٢"])

    assert choice.status_code == 422 and choice.json()["code"] == "validation_error"
    assert hidden.status_code == 404 and hidden.json() == missing.json()
    assert missing.json()["code"] == "practice_item_not_found"
    assert foreign_source.status_code == 422 and foreign_source.json()["code"] == "source_not_found"
    assert not_a_source.status_code == 422
    assert {too_many.status_code, zero_points.status_code, long_reference.status_code} == {422}
    assert {huge_item.status_code, huge_source.status_code} == {422}
    assert out_of_range_source.json()["code"] == "source_not_found"
    assert arabic_digits.json()["code"] == "source_not_found"
    db.expire_all()
    assert mcq.rubric.origin == "generated"  # hiçbiri bir şey değiştirmedi
    assert db.scalar(select(PracticeRubric).where(PracticeRubric.question_id.is_(None))) is None
    assert db.scalar(select(PracticeRubricRevision)) is None  # reddedilen giriş iz bırakmaz


def test_question_from_another_course_is_not_found(db, client_for, setup) -> None:
    s = setup
    question = open_question(db, s)

    other_course_id = db.scalar(
        select(Enrollment.course_id).where(Enrollment.user_id == s.other.id)
    )
    response = client_for(s.other).post(
        f"/instructor/courses/{other_course_id}/rubrics",
        json={**RUBRIC_IN, "practice_item_id": question.id},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "practice_item_not_found"


def test_rubric_permissions_and_listing(db, client_for, setup) -> None:
    s = setup
    question = open_question(db, s)
    open_question(db, s, status="rejected")  # öğrenciye hiç gitmedi: listede yok
    path = f"/instructor/courses/{s.course.id}/rubrics"

    ta_create = post_rubric(client_for(s.ta), s, practice_item_id=question.id)
    student_create = post_rubric(client_for(s.students[0]), s)
    outsider_create = post_rubric(client_for(s.other), s)
    concept = post_rubric(client_for(s.instructor), s).json()
    listed = client_for(s.ta).get(path)

    assert ta_create.status_code == 403 and student_create.status_code == 403
    assert outsider_create.status_code == 404
    assert listed.status_code == 200, listed.text
    assert [r["id"] for r in listed.json()] == [concept["id"], question.rubric.id]
    assert listed.json()[1]["origin"] == "generated" and listed.json()[1]["approved"] is False
    assert client_for(s.students[0]).get(path).status_code == 403


def test_rubric_list_puts_the_last_changed_first(db, client_for, setup) -> None:
    s = setup
    older, newer = open_question(db, s), open_question(db, s)
    instructor = client_for(s.instructor)
    path = f"/instructor/courses/{s.course.id}/rubrics"
    before = [r["practice_item_id"] for r in instructor.get(path).json()]

    post_rubric(instructor, s, practice_item_id=older.id)
    after = [r["practice_item_id"] for r in instructor.get(path).json()]

    assert before == [newer.id, older.id]
    assert after == [older.id, newer.id]


def test_replaced_rubrics_keep_every_earlier_version(db, client_for, setup) -> None:
    """Üretilen ilk hâl ve eğitmenin önceki düzeltmesi kaybolmaz; soru silinince geçmiş de gider."""
    s = setup
    question = open_question(db, s)
    instructor = client_for(s.instructor)

    first = post_rubric(instructor, s, practice_item_id=question.id)
    second = post_rubric(
        instructor,
        s,
        practice_item_id=question.id,
        reference_answer="Aralık her adımda yarıya iner.",
    )
    post_rubric(instructor, s)  # kavram rubriği: yeni satır, geçmiş yok

    assert first.status_code == 200 and second.status_code == 200
    revisions = db.scalars(select(PracticeRubricRevision).order_by(PracticeRubricRevision.id)).all()
    assert [(r.origin, r.approved, r.reference_answer) for r in revisions] == [
        ("generated", False, "Yarıyı atar."),
        ("instructor", True, RUBRIC_IN["reference_answer"]),
    ]
    assert {r.rubric_id for r in revisions} == {question.rubric.id}
    assert revisions[0].criteria == [{"description": "Doğru şık", "points": 1}]
    assert all(r.replaced_by == s.instructor.id and r.replaced_at for r in revisions)

    db.delete(question)
    db.commit()
    assert db.scalar(select(PracticeRubricRevision)) is None
