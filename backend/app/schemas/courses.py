from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Role

Level = Literal["undergraduate", "graduate"]


class CourseInfo(BaseModel):
    """Dersin tanıtım bilgileri; eğitmen girer, hepsi boş olabilir."""

    instructor_name: str | None = Field(default=None, max_length=200)
    term: str | None = Field(default=None, max_length=64)
    level: Level | None = None
    department: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)

    @field_validator("instructor_name", "term", "department", "description")
    @classmethod
    def blank_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class CourseSummary(CourseInfo):
    """Ders = izolasyon birimi; her dersin ayrı indeksi vardır."""

    id: int
    code: str
    name: str
    language: Literal["tr", "en"]
    # Kimlik doğrulama gelene kadar boş.
    role: Role | None = None


class CourseCreate(CourseInfo):
    code: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=2, max_length=200)
    language: Literal["tr", "en"] = "tr"

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return "".join(value.split()).upper()

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class CourseUpdate(CourseInfo):
    """Kısmi güncelleme: yalnızca gönderilen alanlar değişir (boş metin alanı temizler)."""

    name: str | None = Field(default=None, min_length=2, max_length=200)
    language: Literal["tr", "en"] | None = None
