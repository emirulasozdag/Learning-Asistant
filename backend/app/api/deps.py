from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import Course
from app.db.session import SessionLocal, get_db

DbSession = Annotated[Session, Depends(get_db)]


def get_session_factory() -> Callable[[], Session]:
    """Akışlı (SSE) cevaplar kendi oturumunu açar: istek bağımlılığı akış bitmeden kapanabilir."""
    return SessionLocal


SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


def get_course_or_404(db: Session, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ders bulunamadı")
    return course
