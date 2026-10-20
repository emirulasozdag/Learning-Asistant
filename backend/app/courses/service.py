import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Enrollment, User
from app.schemas.common import Role
from app.schemas.courses import CourseCreate, CourseInfo, CourseSummary, CourseUpdate, JoinCode

# Katılım kodu: karışan karakterler (0/O, 1/I) yok; 10 karakter ≈ 50 bit.
_JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_JOIN_LENGTH = 10


class CourseExists(ValueError):
    pass


class InvalidJoinCode(LookupError):
    pass


def list_courses(db: Session, user_id: int) -> list[CourseSummary]:
    """Kullanıcının üye olduğu dersler ve oradaki rolü (ADR-2)."""
    rows = db.execute(
        select(Course, Enrollment.role)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .where(Enrollment.user_id == user_id)
        .order_by(Course.code)
    ).all()
    return [to_summary(course, role) for course, role in rows]


def create_course(db: Session, data: CourseCreate, creator: User) -> CourseSummary:
    """Dersi açan kullanıcı o dersin eğitmeni olur; katılım kodu üretilir (ADR-2)."""
    if db.scalar(select(Course).where(Course.code == data.code)) is not None:
        raise CourseExists(data.code)
    creator_id = creator.id  # rollback nesneleri süresiz bırakır; kimlik önceden alınır
    course = Course(
        code=data.code,
        name=data.name,
        language=data.language,
        **data.model_dump(include=set(CourseInfo.model_fields)),
    )
    _set_new_join_code(db, course)
    db.add(course)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise CourseExists(data.code) from exc
    db.add(Enrollment(user_id=creator_id, course_id=course.id, role="instructor"))
    try:
        db.commit()
    except IntegrityError as exc:  # Aynı kodla eşzamanlı ders açma.
        db.rollback()
        raise CourseExists(data.code) from exc
    return to_summary(course, "instructor")


def update_course(db: Session, course: Course, data: CourseUpdate, role: Role) -> CourseSummary:
    """Yalnızca istekte gönderilen alanları değiştirir."""
    for field, value in data.model_dump(exclude_unset=True).items():
        if field in {"name", "language"} and value is None:
            continue
        setattr(course, field, value)
    db.commit()
    return to_summary(course, role)


def join_course(db: Session, code: str, user: User) -> CourseSummary:
    """Katılım koduyla öğrenci olarak katılır. Zaten üyeyse rolü değişmez."""
    normalized = normalize_join_code(code)
    course = db.scalar(select(Course).where(Course.join_code == normalized)) if normalized else None
    if (
        course is None
        or course.join_code_expires_at is None
        or course.join_code_expires_at <= datetime.now(UTC)
    ):
        raise InvalidJoinCode(code)
    role = db.scalar(
        select(Enrollment.role).where(
            Enrollment.user_id == user.id, Enrollment.course_id == course.id
        )
    )
    if role is None:
        db.add(Enrollment(user_id=user.id, course_id=course.id, role="student"))
        try:
            db.commit()
        except IntegrityError:
            # Aynı anda iki katılım isteği: ikincisi var olan üyeliği kullanır.
            db.rollback()
        role = db.scalar(
            select(Enrollment.role).where(
                Enrollment.user_id == user.id, Enrollment.course_id == course.id
            )
        )
    return to_summary(course, role)  # type: ignore[arg-type]


def join_code(db: Session, course: Course) -> JoinCode:
    """Dersin katılım kodu. Kodu olmayan derse (seed ya da betikle açılmış) ilk istekte üretilir."""
    if course.join_code is None:
        _set_new_join_code(db, course)
        db.commit()
    return JoinCode(code=course.join_code or "", expires_at=course.join_code_expires_at)


def rotate_join_code(db: Session, course: Course) -> JoinCode:
    """Yeni kod üretir; eski kod hemen geçersiz olur (sızdıysa yenilenir, ADR-2)."""
    _set_new_join_code(db, course)
    db.commit()
    return join_code(db, course)


def normalize_join_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isascii() and ch.isalnum())


def _set_new_join_code(db: Session, course: Course) -> None:
    while True:
        code = "".join(secrets.choice(_JOIN_ALPHABET) for _ in range(_JOIN_LENGTH))
        if db.scalar(select(Course.id).where(Course.join_code == code)) is None:
            break
    course.join_code = code
    course.join_code_expires_at = datetime.now(UTC) + timedelta(days=settings.join_code_ttl_days)


def to_summary(course: Course, role: Role) -> CourseSummary:
    return CourseSummary(
        id=course.id,
        code=course.code,
        name=course.name,
        language=course.language,
        instructor_name=course.instructor_name,
        term=course.term,
        level=course.level,
        department=course.department,
        description=course.description,
        role=role,
    )
