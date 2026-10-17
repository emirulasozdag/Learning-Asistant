from pydantic import BaseModel


class Citation(BaseModel):
    """Bir cevabın dayandığı kaynak parçası: sayfa ve/veya video zamanı (sunum slayt 4)."""

    source_id: str
    document_title: str | None = None
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
