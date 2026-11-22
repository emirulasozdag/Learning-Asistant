"""Sunum modu (DEMO_LOGIN): varsayılan kapalı; açıkken yalnızca ayardaki geliştirme hesapları."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.demo import enroll_dev_instructor
from app.core.config import settings
from app.db.models import Course, Enrollment, User
from tests.conftest import TEST_DATABASE_URL, enroll, make_user

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL tanımlı değil")


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch, db: Session, user: User, course: Course) -> User:
    """Demo açık: `user` geliştirme eğitmeni, yeni bir öğrenci geliştirme öğrencisi."""
    student = make_user(db, "demo-ogrenci@example.com")
    enroll(db, student, course, "student")
    monkeypatch.setattr(settings, "demo_login", True)
    monkeypatch.setattr(settings, "dev_instructor_email", user.email)
    monkeypatch.setattr(settings, "dev_student_email", student.email)
    return student


def test_demo_is_hidden_when_off(
    monkeypatch: pytest.MonkeyPatch, client_for: Callable[[User | None], TestClient]
) -> None:
    # Uygulamanın varsayılanı kapalıdır; yerel .env açmış olabileceği için burada açıkça kapatılır.
    monkeypatch.setattr(settings, "demo_login", False)
    client = client_for(None)

    assert client.get("/auth/demo").status_code == 404
    assert client.post("/auth/demo-login", json={"role": "student"}).status_code == 404


def test_demo_lists_dev_accounts_and_join_codes(
    client_for: Callable[[User | None], TestClient], demo: User, course: Course
) -> None:
    info = client_for(None).get("/auth/demo").json()

    assert [(a["role"], a["email"]) for a in info["accounts"]] == [
        ("instructor", "egitmen@example.com"),
        ("student", "demo-ogrenci@example.com"),
    ]
    assert [(c["code"], c["course_id"]) for c in info["courses"]] == [(course.code, course.id)]
    assert info["courses"][0]["join_code"]


def test_demo_login_opens_a_session_for_the_configured_account_only(
    client_for: Callable[[User | None], TestClient], demo: User
) -> None:
    client = client_for(None)

    # İstemci e-posta gönderse de dikkate alınmaz: hesap ayardan seçilir.
    response = client.post(
        "/auth/demo-login", json={"role": "student", "email": "egitmen@example.com"}
    )

    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/me").json()["user"]["email"] == "demo-ogrenci@example.com"
    assert client.post("/auth/demo-login", json={"role": "admin"}).status_code == 422


def test_imported_course_is_given_to_the_dev_instructor_only_when_dev_accounts_are_on(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    instructor = make_user(db, "demo-egitmen@example.com", can_create_courses=True)
    imported = Course(code="6.006", name="Introduction to Algorithms", language="en")
    db.add(imported)
    db.commit()
    monkeypatch.setattr(settings, "dev_instructor_email", instructor.email)

    monkeypatch.setattr(settings, "seed_dev_accounts", False)
    assert enroll_dev_instructor(db, imported) is False

    monkeypatch.setattr(settings, "seed_dev_accounts", True)
    assert enroll_dev_instructor(db, imported) is True
    # Tekrar çalıştırılabilir: ikinci kez üyelik eklenmez.
    assert enroll_dev_instructor(db, imported) is False
    role = db.scalar(
        select(Enrollment.role).where(
            Enrollment.user_id == instructor.id, Enrollment.course_id == imported.id
        )
    )
    assert role == "instructor"


def test_demo_course_can_be_turned_off(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    """SEED_DEMO_COURSE=false: silinen demo dersi geri gelmez; hesaplar derssiz oluşturulur."""
    from app.auth.passwords import MIN_PASSWORD_LENGTH
    from app.scripts.seed_demo import DEMO_COURSE, demo_course, seed_dev_accounts

    def demo_courses() -> int:
        return len(db.scalars(select(Course).where(Course.code == DEMO_COURSE["code"])).all())

    before = demo_courses()
    monkeypatch.setattr(settings, "seed_demo_course", False)
    monkeypatch.setattr(settings, "dev_instructor_email", "seed-egitmen@example.com")
    monkeypatch.setattr(settings, "dev_instructor_password", "e" * MIN_PASSWORD_LENGTH)
    monkeypatch.setattr(settings, "dev_student_email", "seed-ogrenci@example.com")
    monkeypatch.setattr(settings, "dev_student_password", "o" * MIN_PASSWORD_LENGTH)

    assert demo_course(db) is None
    seed_dev_accounts(db, None)

    assert demo_courses() == before
    users = db.scalars(
        select(User).where(User.email.in_(["seed-egitmen@example.com", "seed-ogrenci@example.com"]))
    ).all()
    assert len(users) == 2
    assert not db.scalars(
        select(Enrollment).where(Enrollment.user_id.in_([u.id for u in users]))
    ).all()

    monkeypatch.setattr(settings, "seed_demo_course", True)
    course = demo_course(db)
    assert course is not None and course.code == DEMO_COURSE["code"]
