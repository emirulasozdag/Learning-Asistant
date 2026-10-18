from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.schemas.sources import SourceDetail
from app.sources.lookup import get_source as lookup_source

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str, db: DbSession) -> SourceDetail:
    """FR-18: alıntıya tıklanınca ilgili parça ve orijinal dosyada o sayfa."""
    source = lookup_source(db, source_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Kaynak bulunamadı")
    return source
