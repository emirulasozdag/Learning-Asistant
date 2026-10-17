from pydantic import BaseModel

from app.schemas.materials import MaterialType


class SourceDetail(BaseModel):
    """Kaynak görüntüleyicide açılacak alıntı: metin + sayfa veya video anı."""

    source_id: str
    document_id: int
    document_title: str
    material_type: MaterialType
    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
    media_url: str | None = None
