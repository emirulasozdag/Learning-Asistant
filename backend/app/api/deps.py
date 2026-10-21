from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, not_found_error, require_course_role
from app.db.models import Course, Document
from app.db.session import SessionLocal, get_db
from app.ingestion.transcribe import Transcriber, get_transcriber
from app.schemas.ask import VideoRef
from app.schemas.common import Role
from app.schemas.materials import MaterialType

DbSession = Annotated[Session, Depends(get_db)]


def get_session_factory() -> Callable[[], Session]:
    """Akışlı (SSE) cevaplar kendi oturumunu açar: istek bağımlılığı akış bitmeden kapanabilir."""
    return SessionLocal


SessionFactory = Annotated[Callable[[], Session], Depends(get_session_factory)]


TranscriberDep = Annotated[Transcriber, Depends(get_transcriber)]


def get_course_for(db: Session, user: CurrentUser, course_id: int, *roles: Role) -> Course:
    """Kullanıcının üye olduğu (ve verildiyse o role sahip olduğu) ders; değilse 404/403."""
    require_course_role(user, course_id, *roles)
    course = db.get(Course, course_id)
    if course is None:
        raise not_found_error("course_not_found")
    return course


def checked_video(db: Session, course: Course, video: VideoRef | None) -> VideoRef | None:
    """Verilen video bu dersin onaylı bir video dokümanı olmalı (değilse 422); zaman süreye
    kırpılır. `/ask` ve `/tutor` aynı denetimi kullanır."""
    if video is None:
        return None
    document = db.get(Document, video.document_id)
    if (
        document is None
        or document.course_id != course.id
        or document.material_type != MaterialType.VIDEO
        or document.approved_at is None
        or document.status != "ready"
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Seçilen video bu derse ait bir video değil.",
        )
    time_s = video.time_s
    if document.duration_s is not None:
        time_s = min(time_s, document.duration_s)
    return VideoRef(document_id=document.id, time_s=time_s)
