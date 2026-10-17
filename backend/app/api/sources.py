from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.sources import SourceDetail

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("/{source_id}", response_model=SourceDetail)
def get_source(source_id: str) -> SourceDetail:
    """FR-18: alıntıya tıklanınca ilgili sayfa / video anı (ders erişimi kontrol edilir)."""
    not_implemented("Kaynak görüntüleyici")
