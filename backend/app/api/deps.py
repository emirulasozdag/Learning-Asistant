from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.dependencies import CurrentUser, not_found_error, require_course_role
from app.db.models import Course, Document, VideoFrame
from app.db.session import SessionLocal, get_db
from app.retrieval.frames import frames_overlapping
from app.schemas.ask import VideoRef
from app.schemas.common import Role
from app.schemas.materials import MaterialType

DbSession = Annotated[Session, Depends(get_db)]

# Öğrencinin seçtiği kare, durdurulan an karenin aralığından bu kadar (saniye) taşsa da kabul
# edilir: oynatıcı ile kare zamanları arasında örnekleme (0,5 sn) farkı olabilir.
FRAME_TIME_TOLERANCE_S = 1.0


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


def checked_video(db: Session, course: Course, video: VideoRef | None) -> VideoRef | None:
    """İsteğin video bağlamını doğrular; `/ask` ve `/tutor` aynı denetimi kullanır (#14, #25).

    - Video bu dersin onaylı ve hazır bir video dokümanı olmalı; değilse 422 `invalid_video`
      (başka dersin videosu da aynı yanıtı alır: varlığı sızdırılmaz).
    - Zaman videonun süresine kırpılır.
    - Kare verildiyse bu videonun karesi olmalı ve o anda ekranda olmalı (`FRAME_TIME_TOLERANCE_S`
      payıyla); değilse 422 `invalid_frame`. Verilmediyse o anda ekrandaki kare seçilir.

    Dönen `VideoRef` yetkilendirilmiş bağlamdır: cevap ve soru kaydı bunu kullanır.
    """
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
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Seçilen video bu derse ait bir video değil.",
            "invalid_video",
        )
    time_s = video.time_s
    if document.duration_s is not None:
        time_s = min(time_s, document.duration_s)
    return VideoRef(
        document_id=document.id,
        time_s=time_s,
        frame_id=_authorized_frame(db, document, time_s, video.frame_id),
    )


def _authorized_frame(
    db: Session, document: Document, time_s: float, frame_id: int | None
) -> int | None:
    if frame_id is None:
        on_screen = frames_overlapping(db, document.id, time_s, time_s)
        return on_screen[0].id if on_screen else None
    frame = db.get(VideoFrame, frame_id)
    on_screen = frame is not None and (
        frame.t_start - FRAME_TIME_TOLERANCE_S <= time_s <= frame.t_end + FRAME_TIME_TOLERANCE_S
    )
    if frame is None or frame.document_id != document.id or not on_screen:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Seçilen kare bu videonun durdurulan anına ait değil.",
            "invalid_frame",
        )
    return frame.id
