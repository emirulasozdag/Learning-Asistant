from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CourseSummary(BaseModel):
    """Ders = izolasyon birimi; her dersin ayrı indeksi vardır."""

    id: int
    code: str
    name: str
    language: Literal["tr", "en"]
    # Kimlik doğrulama gelene kadar boş.
    role: Literal["student", "instructor", "ta"] | None = None


class CourseCreate(BaseModel):
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
