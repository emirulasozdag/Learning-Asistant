from enum import StrEnum

from pydantic import BaseModel

from app.schemas.common import Citation


class PracticeType(StrEnum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    CODE_TRACING = "code_tracing"


class PracticeRequest(BaseModel):
    course_id: int
    type: PracticeType
    topic: str | None = None
    source_id: str | None = None


class PracticeItem(BaseModel):
    """Tek bir kaynak pasaja bağlı, otomatik kontrollerden geçmiş pratik sorusu."""

    id: int
    type: PracticeType
    prompt: str
    options: list[str] | None = None
    source: Citation
