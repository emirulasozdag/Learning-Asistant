"""Kimlik doğrulama ve ders düzeyinde yetki testleri (#11, gerçek veritabanı).

Konular: kayıt/giriş/çıkış, onay (ADR-4), katılım kodu (ADR-2), ders dışı erişimin 404'ü,
rol sınırları, sohbet sahipliği, hesap/veri silme, anonim analitik ve CSRF origin denetimi.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api import ask as ask_api
from app.core.config import settings
from app.db.models import AuthSession, Conversation, Course, Document, Enrollment, Message, User
from tests.conftest import TEST_PASSWORD, enroll, make_user
from tests.test_answer import FakeLLM
from tests.test_flow import upload

QUESTION = "Neden sag yari elenir?"
RUBRIC = {
    "concept": "Ikili arama",
    "reference_answer": "Dizi sirali oldugu icin yari elenir.",
    "criteria": [{"description": "Siralilik", "points": 1}],
}


def ask(client: TestClient, course_id: int, question: str = QUESTION, **extra):
    return client.post("/ask", json={"course_id": course_id, "question": question, **extra})


def assert_error(response, status: int, code: str) -> None:
    assert response.status_code == status, response.text
    assert response.json()["code"] == code


def register(client: TestClient, email: str = "yeni@example.com", password: str = TEST_PASSWORD):
    return client.post(
        "/auth/register", json={"name": "Yeni Kisi", "email": email, "password": password}
    )


def make_course(db, code: str, instructor: User) -> Course:
    other = Course(code=code, name=f"Ders {code}", language="tr")
    db.add(other)
    db.commit()
    enroll(db, instructor, other, "instructor")
    return other


@pytest.fixture
def world(db, client_for, user, course, sample_pdf: Path) -> SimpleNamespace:
    """Ders A (eğitmen `user`, yüklenmiş pdf), öğrenci, TA, ders dışı kullanıcı ve B dersinin
    eğitmeni."""
    document = upload(client_for(user), course.id, sample_pdf).json()
    chunk = client_for(user).get(f"/documents/{document['id']}/chunks").json()[1]
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    ta = make_user(db, "ta@example.com")
    enroll(db, ta, course, "ta")
    outsider = make_user(db, "disaridan@example.com")
    other_instructor = make_user(db, "baska@example.com", can_create_courses=True)
    course_b = make_course(db, "FIZ101", other_instructor)
    return SimpleNamespace(
        course=course,
        course_b=course_b,
        instructor=user,
        student=student,
        ta=ta,
        outsider=outsider,
        other_instructor=other_instructor,
        doc=document["id"],
        chunk=str(chunk["id"]),
    )


# --- 1. Kayıt / giriş / çıkış ---


def test_register_sets_httponly_cookie_and_gives_empty_me(client_for) -> None:
    response = register(client_for(None))

    assert response.status_code == 201
    assert "httponly" in response.headers["set-cookie"].lower()
    assert settings.session_cookie_name in response.headers["set-cookie"]
    body = response.json()
    assert body["user"]["can_create_courses"] is False
    assert body["memberships"] == []
    assert body["consent"]["consented_at"] is None
    assert body["consent"]["policy_version"] == ""


def test_register_duplicate_email_ignoring_case_is_409(client_for) -> None:
    register(client_for(None), "Ayse@Example.com")

    assert_error(register(client_for(None), "ayse@example.COM"), 409, "email_exists")


@pytest.mark.parametrize(
    ("email", "password"), [("a@example.com", "kisa"), ("gecersiz-eposta", TEST_PASSWORD)]
)
def test_register_rejects_bad_input(client_for, email: str, password: str) -> None:
    assert_error(register(client_for(None), email, password), 422, "validation_error")


def test_register_cannot_grant_instructor_power(client_for) -> None:
    client = client_for(None)
    client.post(
        "/auth/register",
        json={
            "name": "Hileci",
            "email": "hileci@example.com",
            "password": TEST_PASSWORD,
            "role": "instructor",
            "can_create_courses": True,
        },
    )

    response = client.post("/courses", json={"code": "HIL101", "name": "Hileli Ders"})

    assert_error(response, 403, "insufficient_role")


@pytest.mark.parametrize(
    ("email", "password"),
    [("egitmen@example.com", "yanlis-sifre-1"), ("yok@example.com", TEST_PASSWORD)],
)
def test_login_with_wrong_credentials_is_401(client_for, user, email: str, password: str) -> None:
    response = client_for(None).post("/auth/login", json={"email": email, "password": password})

    assert_error(response, 401, "not_authenticated")


def test_login_with_upper_case_email_works(client_for, user) -> None:
    client = client_for(None)

    response = client.post(
        "/auth/login", json={"email": "EGITMEN@Example.com", "password": TEST_PASSWORD}
    )

    assert response.status_code == 200
    me = client.get("/me").json()["user"]
    assert me["email"] == "egitmen@example.com"
    # Eğitmen hesabı: arayüz hiç dersi yokken de eğitmen ana sayfasını açar.
    assert me["can_create_courses"] is True


def test_logout_invalidates_the_token(client_for, user) -> None:
    client = client_for(None)
    client.post("/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    token = client.cookies.get(settings.session_cookie_name)

    assert client.post("/auth/logout").status_code == 204

    replay = client_for(None)
    replay.cookies.set(settings.session_cookie_name, token)
    assert_error(replay.get("/me"), 401, "not_authenticated")


def test_expired_session_is_rejected(client: TestClient, db) -> None:
    assert client.get("/me").status_code == 200
    for session in db.scalars(select(AuthSession)):
        session.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    assert_error(client.get("/me"), 401, "not_authenticated")


# --- 2. Oturumsuz erişim ---


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/courses"),
        ("GET", "/me"),
        ("POST", "/ask"),
        ("GET", "/sources/1"),
        ("GET", "/documents/1/file"),
        ("GET", "/courses/1/materials"),
    ],
)
def test_unauthenticated_requests_are_401(client_for, method: str, path: str) -> None:
    response = client_for(None).request(method, path)

    assert_error(response, 401, "not_authenticated")


# --- 3. Onay (ADR-4) ---


def test_ask_requires_consent(db, client_for, world) -> None:
    pending = make_user(db, "onaysiz@example.com", consented=False)
    enroll(db, pending, world.course, "student")

    assert_error(ask(client_for(pending), world.course.id), 403, "consent_required")


def test_consent_flow_unlocks_ask_and_reflects_research_logging(db, client_for, world) -> None:
    pending = make_user(db, "onaysiz@example.com", consented=False)
    enroll(db, pending, world.course, "student")
    client = client_for(pending)

    wrong = client.put("/me/consent", json={"policy_version": "eski", "research_logging": True})
    right = client.put(
        "/me/consent",
        json={"policy_version": settings.privacy_policy_version, "research_logging": True},
    )

    assert_error(wrong, 422, "validation_error")
    assert right.status_code == 200
    assert ask(client, world.course.id).status_code == 200
    consent = client.get("/me").json()["consent"]
    assert consent["research_logging"] is True
    assert consent["policy_version"] == settings.privacy_policy_version


# --- 4. Katılım kodu (ADR-2) ---


def join_code(client: TestClient, course_id: int) -> str:
    """Fixture dersinin kodu yoktur: önce üretilir, GET aynı kodu döndürmelidir."""
    created = client.post(f"/courses/{course_id}/join-code").json()["code"]
    assert client.get(f"/courses/{course_id}/join-code").json()["code"] == created
    return created


def test_join_with_sloppy_code_makes_student_and_lists_course(client_for, world) -> None:
    code = join_code(client_for(world.instructor), world.course.id)
    client = client_for(world.outsider)
    assert client.get("/courses").json() == []

    response = client.post(
        "/courses/join", json={"code": f" {code[:5].lower()} {code[5:].lower()} "}
    )

    assert response.status_code == 200 and response.json()["role"] == "student"
    assert [c["id"] for c in client.get("/courses").json()] == [world.course.id]
    assert client.post("/courses/join", json={"code": code}).json()["role"] == "student"


def test_joining_own_course_keeps_instructor_role(client_for, world) -> None:
    client = client_for(world.instructor)

    response = client.post("/courses/join", json={"code": join_code(client, world.course.id)})

    assert response.json()["role"] == "instructor"


def test_wrong_join_code_is_404(client_for, world) -> None:
    response = client_for(world.outsider).post("/courses/join", json={"code": "YANLIS1234"})

    assert_error(response, 404, "course_not_found")


def test_rotating_join_code_invalidates_old_one(client_for, world) -> None:
    client = client_for(world.instructor)
    old = join_code(client, world.course.id)

    new = client.post(f"/courses/{world.course.id}/join-code").json()["code"]

    other = client_for(world.outsider)
    assert new != old
    assert_error(other.post("/courses/join", json={"code": old}), 404, "course_not_found")
    assert other.post("/courses/join", json={"code": new}).status_code == 200


def test_expired_join_code_is_404(db, client_for, world) -> None:
    code = join_code(client_for(world.instructor), world.course.id)
    world.course.join_code_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    response = client_for(world.outsider).post("/courses/join", json={"code": code})

    assert_error(response, 404, "course_not_found")


def test_join_code_is_only_for_instructors(client_for, world) -> None:
    path = f"/courses/{world.course.id}/join-code"

    assert_error(client_for(world.student).get(path), 403, "insufficient_role")
    assert_error(client_for(world.outsider).get(path), 404, "course_not_found")


# --- 5. Ders dışı kullanıcı ve başka dersin eğitmeni: doğrudan kimlikle erişim ---

# (yöntem, yol, istek parametreleri, beklenen hata kodu); kimlikler (ders, doküman, parça)
ISOLATION_CASES = {
    "source": lambda c, d, s: ("GET", f"/sources/{s}", {}, "source_not_found"),
    "chunks": lambda c, d, s: ("GET", f"/documents/{d}/chunks", {}, "document_not_found"),
    "file": lambda c, d, s: ("GET", f"/documents/{d}/file", {}, "document_not_found"),
    "page_image": lambda c, d, s: ("GET", f"/documents/{d}/pages/1.png", {}, "document_not_found"),
    "delete_document": lambda c, d, s: ("DELETE", f"/documents/{d}", {}, "document_not_found"),
    "list_materials": lambda c, d, s: ("GET", f"/courses/{c}/materials", {}, "course_not_found"),
    "upload": lambda c, d, s: (
        "POST",
        f"/courses/{c}/materials",
        {
            "data": {"material_type": "notes", "declaration": "true"},
            "files": {"file": ("a.pdf", b"%PDF-1.4")},
        },
        "course_not_found",
    ),
    "patch_course": lambda c, d, s: (
        "PATCH",
        f"/courses/{c}",
        {"json": {"term": "Guz"}},
        "course_not_found",
    ),
    "activity": lambda c, d, s: (
        "GET",
        f"/instructor/courses/{c}/activity",
        {},
        "course_not_found",
    ),
    "ask": lambda c, d, s: (
        "POST",
        "/ask",
        {"json": {"course_id": c, "question": QUESTION}},
        "course_not_found",
    ),
    "ask_stream": lambda c, d, s: (
        "POST",
        "/ask/stream",
        {"json": {"course_id": c, "question": QUESTION}},
        "course_not_found",
    ),
    "practice": lambda c, d, s: (
        "POST",
        "/practice",
        {"json": {"course_id": c, "type": "mcq"}},
        "course_not_found",
    ),
    "learning_record": lambda c, d, s: (
        "GET",
        f"/courses/{c}/learning-record",
        {},
        "course_not_found",
    ),
    "rubrics_get": lambda c, d, s: (
        "GET",
        f"/instructor/courses/{c}/rubrics",
        {},
        "course_not_found",
    ),
    "rubrics_post": lambda c, d, s: (
        "POST",
        f"/instructor/courses/{c}/rubrics",
        {"json": RUBRIC},
        "course_not_found",
    ),
}


@pytest.mark.parametrize("actor", ["outsider", "other_instructor"])
@pytest.mark.parametrize("case", list(ISOLATION_CASES))
def test_non_members_get_404_identical_to_nonexistent_ids(
    client_for, world, actor: str, case: str
) -> None:
    client = client_for(getattr(world, actor))
    build = ISOLATION_CASES[case]

    method, path, kwargs, code = build(world.course.id, world.doc, world.chunk)
    forbidden = client.request(method, path, **kwargs)
    method, path, kwargs, code = build(99999, 99999, "99999")
    missing = client.request(method, path, **kwargs)

    assert_error(forbidden, 404, code)
    assert_error(missing, 404, code)
    assert forbidden.json() == missing.json()


# --- 6. Dersin içinde roller ---


def test_student_can_read_materials_and_ask(client_for, world) -> None:
    client = client_for(world.student)

    assert client.get(f"/sources/{world.chunk}").status_code == 200
    assert client.get(f"/documents/{world.doc}/file").status_code == 200
    assert client.get(f"/documents/{world.doc}/chunks").status_code == 200
    assert len(client.get(f"/courses/{world.course.id}/materials").json()) == 1
    assert ask(client, world.course.id).status_code == 200


def test_student_cannot_manage_the_course(client_for, world, sample_pdf: Path) -> None:
    client = client_for(world.student)
    course_id = world.course.id

    responses = [
        upload(client, course_id, sample_pdf),
        client.delete(f"/documents/{world.doc}"),
        client.patch(f"/courses/{course_id}", json={"term": "Guz"}),
        client.get(f"/instructor/courses/{course_id}/activity"),
        client.get(f"/instructor/courses/{course_id}/rubrics"),
        client.post(f"/instructor/courses/{course_id}/rubrics", json=RUBRIC),
        client.get(f"/instructor/courses/{course_id}/mistakes"),
    ]

    for response in responses:
        assert_error(response, 403, "insufficient_role")


def test_ta_sees_activity_but_cannot_write_rubrics(client_for, world) -> None:
    client = client_for(world.ta)
    course_id = world.course.id

    assert client.get(f"/instructor/courses/{course_id}/activity").status_code == 200
    assert client.get(f"/instructor/courses/{course_id}/rubrics").status_code == 501
    assert_error(
        client.post(f"/instructor/courses/{course_id}/rubrics", json=RUBRIC),
        403,
        "insufficient_role",
    )


# --- 7. İskelet uçlar ---


def test_skeleton_routes_return_501_for_authorised_members(client_for, world) -> None:
    course_id = world.course.id
    student, instructor = client_for(world.student), client_for(world.instructor)

    assert student.get(f"/courses/{course_id}/learning-record").status_code == 501
    assert instructor.get(f"/instructor/courses/{course_id}/mistakes").status_code == 501
    assert instructor.get(f"/instructor/courses/{course_id}/rubrics").status_code == 501
    assert (
        instructor.post(f"/instructor/courses/{course_id}/rubrics", json=RUBRIC).status_code == 501
    )
    review = {"target_type": "message", "target_id": 1, "decision": "approve"}
    assert instructor.post("/instructor/reviews", json=review).status_code == 501


# --- 8. Yükleme beyanı ---


def test_upload_without_declaration_is_rejected(db, client_for, world, sample_pdf: Path) -> None:
    before = db.scalar(select(func.count(Document.id)))

    with sample_pdf.open("rb") as file:
        response = client_for(world.instructor).post(
            f"/courses/{world.course.id}/materials",
            data={"material_type": "notes"},
            files={"file": (sample_pdf.name, file)},
        )

    assert_error(response, 422, "validation_error")
    assert db.scalar(select(func.count(Document.id))) == before


def test_upload_records_who_approved(db, world) -> None:
    document = db.get(Document, world.doc)

    assert document.approved_by == world.instructor.id
    assert document.approved_at is not None


# --- 9. Sohbet sahipliği ---


def test_conversation_belongs_to_its_owner(db, client_for, world) -> None:
    other = make_user(db, "ogrenci2@example.com")
    enroll(db, other, world.course, "student")
    first, second = client_for(world.student), client_for(other)
    conversation_id = ask(first, world.course.id).json()["conversation_id"]

    stolen = ask(second, world.course.id, conversation_id=conversation_id)
    stolen_stream = second.post(
        "/ask/stream",
        json={
            "course_id": world.course.id,
            "question": QUESTION,
            "conversation_id": conversation_id,
        },
    )
    own = ask(first, world.course.id, conversation_id=conversation_id)

    assert_error(stolen, 404, "conversation_not_found")
    assert_error(stolen_stream, 404, "conversation_not_found")
    assert not stolen_stream.headers["content-type"].startswith("text/event-stream")
    assert own.status_code == 200 and own.json()["conversation_id"] == conversation_id


# --- 10. Üyeliğin iptali ---


def test_revoked_membership_ends_access_immediately(db, client_for, world) -> None:
    client = client_for(world.student)
    conversation_id = ask(client, world.course.id).json()["conversation_id"]

    db.query(Enrollment).filter_by(user_id=world.student.id, course_id=world.course.id).delete()
    db.commit()

    assert client.get("/courses").json() == []
    assert_error(client.get(f"/sources/{world.chunk}"), 404, "source_not_found")
    assert_error(ask(client, world.course.id), 404, "course_not_found")
    assert_error(
        ask(client, world.course.id, conversation_id=conversation_id), 404, "course_not_found"
    )


# --- 11. Silme ---


def count(db, model, *where) -> int:
    db.expire_all()
    return db.scalar(select(func.count()).select_from(model).where(*where))


def test_delete_my_data_removes_only_own_conversations(db, client_for, world) -> None:
    other = make_user(db, "ogrenci2@example.com")
    enroll(db, other, world.course, "student")
    mine, theirs = client_for(world.student), client_for(other)
    ask(mine, world.course.id)
    ask(theirs, world.course.id)

    assert mine.delete("/me/data").status_code == 204

    assert count(db, Conversation, Conversation.user_id == world.student.id) == 0
    assert count(db, Conversation, Conversation.user_id == other.id) == 1
    assert count(db, Message) == 2
    assert mine.get("/me").status_code == 200


def test_delete_account_removes_personal_data(db, client_for, world) -> None:
    client = client_for(world.student)
    student_id = world.student.id
    ask(client, world.course.id)
    token = client.cookies.get(settings.session_cookie_name)

    assert client.delete("/me").status_code == 204

    replay = client_for(None)
    replay.cookies.set(settings.session_cookie_name, token)
    assert_error(replay.get("/me"), 401, "not_authenticated")
    assert count(db, User, User.id == student_id) == 0
    assert count(db, Enrollment, Enrollment.user_id == student_id) == 0
    assert count(db, Conversation, Conversation.user_id == student_id) == 0
    assert count(db, Message) == 0


def test_deleting_instructor_account_keeps_the_document(db, client_for, world) -> None:
    assert client_for(world.instructor).delete("/me").status_code == 204

    db.expire_all()
    document = db.get(Document, world.doc)
    assert document is not None and document.approved_by is None


def test_deleting_document_closes_its_sources(client_for, world) -> None:
    student = client_for(world.student)
    assert student.get(f"/sources/{world.chunk}").status_code == 200

    assert client_for(world.instructor).delete(f"/documents/{world.doc}").status_code == 204

    assert_error(student.get(f"/sources/{world.chunk}"), 404, "source_not_found")


# --- 12. Anonim analitik (ADR-4) ---


def activity(client: TestClient, course_id: int) -> dict:
    return client.get(f"/instructor/courses/{course_id}/activity").json()


def add_students(db, course: Course, count_: int, *, research_logging: bool) -> list[User]:
    users = []
    for number in range(count_):
        student = make_user(
            db, f"{'acik' if research_logging else 'kapali'}{number}@example.com",
            research_logging=research_logging,
        )  # fmt: skip
        enroll(db, student, course, "student")
        users.append(student)
    return users


def test_activity_counts_only_opted_in_students(db, client_for, world) -> None:
    opted_in = add_students(db, world.course, 3, research_logging=True)
    opted_out = add_students(db, world.course, 1, research_logging=False)[0]
    for student in opted_in:
        ask(client_for(student), world.course.id)
    ask(client_for(opted_out), world.course.id)
    ask(client_for(world.instructor), world.course.id)

    result = activity(client_for(world.instructor), world.course.id)

    assert result["questions"] == 3 and result["conversations"] == 3


def test_small_groups_are_suppressed(db, client_for, world) -> None:
    students = add_students(db, world.course, 3, research_logging=True)
    instructor = client_for(world.instructor)
    for student in students[:2]:
        ask(client_for(student), world.course.id, "Fransa'nın başkenti neresi?")

    small = activity(instructor, world.course.id)
    ask(client_for(students[2]), world.course.id, QUESTION)
    enough = activity(instructor, world.course.id)

    # İki öğrenci: hiçbir sayı ya da soru gösterilmez.
    assert small["questions"] == 0 and small["recent_questions"] == []
    assert sum(day["questions"] for day in small["daily"]) == 0
    # Üç öğrenci: sayılar ve üç kişiden gelen son sorular görünür; yalnızca iki kişiden gelen
    # "cevapsız" listesi bastırılır.
    assert enough["questions"] == 3 and enough["not_covered"] == 2
    assert len(enough["recent_questions"]) == 3
    assert enough["unanswered_questions"] == []


def test_opting_out_removes_questions_from_activity(db, client_for, world) -> None:
    students = add_students(db, world.course, 3, research_logging=True)
    for student in students:
        ask(client_for(student), world.course.id)
    assert activity(client_for(world.instructor), world.course.id)["questions"] == 3

    client_for(students[0]).put(
        "/me/consent",
        json={"policy_version": settings.privacy_policy_version, "research_logging": False},
    )

    # Geriye iki öğrenci kaldı: küçük grup, özet boş.
    assert activity(client_for(world.instructor), world.course.id)["questions"] == 0


# --- 13. CSRF origin denetimi ---


def test_cross_site_write_is_rejected_but_allowed_origin_passes(client_for) -> None:
    client = client_for(None)

    evil = client.post("/auth/logout", headers={"Origin": "https://evil.example"})
    good = client.post("/auth/logout", headers={"Origin": "http://localhost:5173"})

    assert evil.status_code == 403
    assert good.status_code == 204


# --- 14. Ders oluşturma ---


def test_only_course_creators_can_create_courses(db, client_for, world) -> None:
    body = {"code": "yeni 101", "name": "Yeni Ders"}

    assert_error(client_for(world.student).post("/courses", json=body), 403, "insufficient_role")

    creator = client_for(world.other_instructor)
    created = creator.post("/courses", json=body)
    assert created.status_code == 201 and created.json()["role"] == "instructor"
    assert created.json()["id"] in [c["id"] for c in creator.get("/courses").json()]
    assert creator.get(f"/courses/{created.json()['id']}/join-code").status_code == 200


# --- 15. ADR-5: LLM'e kimlik gitmez ---


def test_llm_never_sees_user_identity(db, client_for, world, monkeypatch) -> None:
    student = make_user(db, "zeynepgizli@ornek-alan.test")
    enroll(db, student, world.course, "student")
    llm = FakeLLM(["Dizi sirali oldugu icin sag yari elenir [S1]."])
    monkeypatch.setattr(ask_api, "select_client", lambda: llm)

    response = ask(client_for(student), world.course.id)

    sent = str(llm.calls)
    assert response.status_code == 200 and llm.calls
    assert student.email not in sent and student.name not in sent
    assert "user_id" not in sent


def test_course_without_join_code_gets_one_on_first_request(client_for, world) -> None:
    """Seed ya da betikle açılan dersin kodu yoktur; eğitmen ilk istediğinde üretilir."""
    instructor = client_for(world.instructor)
    first = instructor.get(f"/courses/{world.course.id}/join-code").json()
    second = instructor.get(f"/courses/{world.course.id}/join-code").json()
    joined = client_for(world.outsider).post("/courses/join", json={"code": first["code"]})

    assert len(first["code"]) == 10 and first == second
    assert joined.status_code == 200 and joined.json()["role"] == "student"


def test_unapproved_document_is_invisible_to_non_instructors(db, client_for, world) -> None:
    """ADR-3 B'ye geçilirse: onaysız doküman öğrenci için hiç yokmuş gibidir (403 değil 404)."""
    document = db.get(Document, world.doc)
    document.approved_at = None
    db.commit()
    student = client_for(world.student)

    assert student.get(f"/courses/{world.course.id}/materials").json() == []
    assert_error(student.delete(f"/documents/{world.doc}"), 404, "document_not_found")
    assert_error(student.get(f"/sources/{world.chunk}"), 404, "source_not_found")
    assert (
        len(client_for(world.instructor).get(f"/courses/{world.course.id}/materials").json()) == 1
    )
