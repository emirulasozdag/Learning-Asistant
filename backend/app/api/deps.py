from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, not_found_error, require_course_role
from app.db.models import Course
from app.db.session import SessionLocal, get_db
from app.schemas.common import Role

DbSession = Annotated[Session, Depends(get_db)]


def get_session_factory() -> Callable[[], Session]:
    """Akışlı (SSE) cevaplar kendi oturumunu açar: istek bağımlılığı akış bitmeden kapanabilir."""
    return SessionLocal


SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


def get_course_for(db: Session, user: CurrentUser, course_id: int, *roles: Role) -> Course:
    """Kullanıcının üye olduğu (ve verildiyse o role sahip olduğu) ders; değilse 404/403."""
    require_course_role(user, course_id, *roles)
    course = db.get(Course, course_id)
    if course is None:
        raise not_found_error("course_not_found")
    return course
