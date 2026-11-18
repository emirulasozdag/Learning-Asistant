from fastapi import APIRouter

from app.api.deps import DbSession
from app.auth.dependencies import AuthUser, CurrentUser, not_found_error, require_course_role
from app.db.models import Document
from app.schemas.sources import SourceDetail
from app.sources.lookup import find_chunk, find_frame, frame_source_detail, source_detail

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, user: AuthUser, db: DbSession) -> SourceDetail:
    """FR-18: alıntıya tıklanınca ilgili parça ve orijinal dosyada o sayfa ya da video aralığı.

    Video parçasında `alternatives`, aynı içeriğin onaylı dokümanlardaki karşılıklarıdır (#19).
    Kare alıntısı (`frame:<kare kimliği>`, #26) videonun o aralığını ve karenin kendisini döndürür
    (#25).

    Yalnızca kaynağın dersinin üyelerine açılır; diğerlerine kaynak yokmuş gibi 404.
    """
    chunk = find_chunk(db, source_id)
    if chunk is not None:
        _require_visible(user, chunk.document)
        return source_detail(db, chunk)
    frame = find_frame(db, source_id)
    document = db.get(Document, frame.document_id) if frame is not None else None
    if frame is None or document is None:
        raise not_found_error("source_not_found")
    _require_visible(user, document)
    return frame_source_detail(frame, document)


def _require_visible(user: CurrentUser, document: Document) -> None:
    """Dersin üyesi değilse ya da doküman onaysız / hazır değilse (eğitmen dışında) 404."""
    role = require_course_role(user, document.course_id, not_found="source_not_found")
    if (document.approved_at is None or document.status != "ready") and role != "instructor":
        raise not_found_error("source_not_found")
