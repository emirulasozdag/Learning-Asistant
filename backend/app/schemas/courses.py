from typing import Literal

from pydantic import BaseModel


class CourseSummary(BaseModel):
    """Ders = izolasyon birimi; her dersin ayrı indeksi vardır."""

    id: int
    code: str
    name: str
    language: Literal["tr", "en"]
    role: Literal["student", "instructor", "ta"]
