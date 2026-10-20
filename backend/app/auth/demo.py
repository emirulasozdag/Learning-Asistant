"""Sunum modu (DEMO_LOGIN): yalnızca yerel demo içindir, üretimde kapalı kalır (ADR-1).

Açıkken giriş ekranı geliştirme hesaplarına (`DEV_INSTRUCTOR_EMAIL`, `DEV_STUDENT_EMAIL`) şifresiz
giriş sunar ve geliştirme eğitmeninin derslerinin katılım kodlarını gösterir. Hangi hesaba
girileceği istemciden gelmez: yalnızca rol seçilir, e-posta ayardan okunur.
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.courses import service as courses
from app.db.models import Course, Enrollment, User
from app.schemas.auth import DemoAccount, DemoCourse, DemoInfo

DemoRole = Literal["instructor", "student"]


def demo_user(db: Session, role: DemoRole) -> User | None:
    email = settings.dev_instructor_email if role == "instructor" else settings.dev_student_email
    return db.scalar(select(User).where(User.email == email.strip().lower()))


def demo_info(db: Session) -> DemoInfo:
    accounts = []
    for role in ("instructor", "student"):
        user = demo_user(db, role)
        if user is not None:
            accounts.append(
                DemoAccount(role=role, name=user.name, email=user.email, title=user.title)
            )

    instructor = demo_user(db, "instructor")
    demo_courses: list[DemoCourse] = []
    if instructor is not None:
        taught = db.scalars(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.user_id == instructor.id, Enrollment.role == "instructor")
            .order_by(Course.code)
        )
        for course in taught:
            # Kodu olmayan derse (betikle açılmış) ilk istekte üretilir.
            code = courses.join_code(db, course).code
            demo_courses.append(
                DemoCourse(course_id=course.id, code=course.code, name=course.name, join_code=code)
            )
    return DemoInfo(accounts=accounts, courses=demo_courses)


def enroll_dev_instructor(db: Session, course: Course) -> bool:
    """Geliştirme hesapları açıksa (SEED_DEV_ACCOUNTS) geliştirme eğitmenini dersin eğitmeni yapar.

    Betikle içeri alınan derslerin (ör. OCW) üyesi olmaz; demo eğitmeni böylece dersi görür.
    Eklendiyse True döner.
    """
    if not settings.seed_dev_accounts:
        return False
    instructor = demo_user(db, "instructor")
    if instructor is None:
        return False
    enrolled = db.scalar(
        select(Enrollment).where(
            Enrollment.user_id == instructor.id, Enrollment.course_id == course.id
        )
    )
    if enrolled is not None:
        return False
    db.add(Enrollment(user_id=instructor.id, course_id=course.id, role="instructor"))
    db.commit()
    return True
