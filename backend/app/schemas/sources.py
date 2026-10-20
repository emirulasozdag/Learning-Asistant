from pydantic import BaseModel

from app.schemas.materials import MaterialType


class Highlight(BaseModel):
    """Sayfa görüntüsü üzerinde alıntılanan satır; koordinatlar sayfaya oranla (0–1)."""

    x: float
    y: float
    width: float
    height: float


class SourceDetail(BaseModel):
    """Kaynak görüntüleyicide açılacak alıntı: metin + sayfa veya video anı."""

    source_id: str
    # Erişim kontrolü için (CONTRACTS.md §1, §3): kaynak yalnızca bu dersin üyelerine açılır.
    course_id: int
    document_id: int
    document_title: str
    material_type: MaterialType
    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
    # Oynatılabilir ya da açılabilir opak URL; video parçasında arayüz t_start'a sarar.
    media_url: str | None = None
    # Yalnızca PDF: sayfanın görüntüsü ve alıntılanan satırların yeri.
    page_image_url: str | None = None
    highlights: list[Highlight] = []
