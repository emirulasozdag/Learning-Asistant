"""Demo dersini oluşturur (yoksa). Kullanım: python -m app.scripts.seed_demo

SEED_DEMO_COURSE=false ise demo dersi oluşturulmaz (silinmişse geri gelmez); geliştirme
hesapları yine oluşturulur ama hiçbir derse eklenmez.

Geliştirme hesapları yalnızca SEED_DEV_ACCOUNTS=true iken ve şifreleri .env'de verilmişse
oluşturulur (DEV_INSTRUCTOR_PASSWORD, DEV_STUDENT_PASSWORD). Üretimde bu ayar kapalı kalır;
çalışma zamanında demo/mock hesap yoktur (ADR-1).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import MIN_PASSWORD_LENGTH, hash_password, verify_password
from app.core.config import settings
from app.db.models import Course, Enrollment, User
from app.db.session import SessionLocal
from app.schemas.common import Role

DEMO_COURSE = {"code": "BLM2512", "name": "Veri Yapıları ve Algoritmalar", "language": "tr"}


def main() -> None:
    with SessionLocal() as db:
        course = demo_course(db)
        if settings.seed_dev_accounts:
            seed_dev_accounts(db, course)


def demo_course(db: Session) -> Course | None:
    if not settings.seed_demo_course:
        print("Demo dersi kapalı (SEED_DEMO_COURSE=false); oluşturulmadı")
        return None
    course = db.scalar(select(Course).where(Course.code == DEMO_COURSE["code"]))
    if course is None:
        course = Course(**DEMO_COURSE)
        db.add(course)
        db.commit()
        print(f"Ders oluşturuldu: {course.code} — {course.name} (id={course.id})")
    else:
        print(f"Ders zaten var: {course.code} (id={course.id})")
    return course


def seed_dev_accounts(db: Session, course: Course | None) -> None:
    accounts: list[tuple[str, str | None, str, str, Role]] = [
        (
            settings.dev_instructor_name,
            settings.dev_instructor_title or None,
            settings.dev_instructor_email,
            settings.dev_instructor_password,
            "instructor",
        ),
        (
            settings.dev_student_name,
            None,
            settings.dev_student_email,
            settings.dev_student_password,
            "student",
        ),
    ]
    for name, title, email, password, role in accounts:
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"{email}: şifre .env'de yok ya da kısa; hesap oluşturulmadı")
            continue
        email = email.strip().lower()
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(
                name=name,
                title=title,
                email=email,
                password_hash=hash_password(password),
                can_create_courses=role == "instructor",
            )
            db.add(user)
            db.flush()
            print(f"Geliştirme hesabı oluşturuldu: {email} ({role})")
        elif not verify_password(user.password_hash, password):
            # Bu e-postayla başkası kayıt olmuş olabilir: var olan hesaba rol verilmez.
            print(f"{email}: aynı e-postayla şifresi farklı bir hesap var; yetki verilmedi")
            continue
        if course is not None:
            enrolled = db.scalar(
                select(Enrollment).where(
                    Enrollment.user_id == user.id, Enrollment.course_id == course.id
                )
            )
            if enrolled is None:
                db.add(Enrollment(user_id=user.id, course_id=course.id, role=role))
        db.commit()


if __name__ == "__main__":
    main()
