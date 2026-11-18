from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation, DbId

Difficulty = Literal["easy", "medium", "hard"]


class PracticeType(StrEnum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    CODE_TRACING = "code_tracing"


class PracticeRequest(BaseModel):
    course_id: int
    type: PracticeType
    # Sınırlar: konu arama sorgusuna ve saklanan soruya gider (#15).
    topic: str | None = Field(default=None, max_length=300)
    source_id: str | None = Field(default=None, max_length=32)
    difficulty: Difficulty | None = None
    # "Bu eksik üzerine çalış": bu denemenin eksiklerine yönelik yeni soru.
    follow_up_of_attempt_id: DbId | None = None


class PracticeItem(BaseModel):
    """Tek bir kaynak pasaja bağlı, otomatik kontrollerden geçmiş pratik sorusu.

    Cevap anahtarı, referans cevap ve açıklama gönderimden önce hiçbir yanıtta dönmez.
    """

    id: int
    course_id: int
    type: PracticeType
    topic: str | None = None
    difficulty: Difficulty
    prompt: str
    # Yalnızca mcq.
    options: list[str] | None = None
    source: Citation
