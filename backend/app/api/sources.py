from fastapi import APIRouter

from app.api.deps import DbSession
from app.auth.dependencies import AuthUser, not_found_error, require_course_role
from app.schemas.sources import SourceDetail
from app.sources.lookup import find_chunk, source_detail

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, user: AuthUser, db: DbSession) -> SourceDetail:
    """FR-18: alıntıya tıklanınca ilgili parça ve orijinal dosyada o sayfa.

    Yalnızca parçanın dersinin üyelerine açılır; diğerlerine kaynak yokmuş gibi 404.
    """
    chunk = find_chunk(db, source_id)
    if chunk is None:
        raise not_found_error("source_not_found")
    role = require_course_role(user, chunk.course_id, not_found="source_not_found")
    if chunk.document.approved_at is None and role != "instructor":
        raise not_found_error("source_not_found")
    return source_detail(chunk)
