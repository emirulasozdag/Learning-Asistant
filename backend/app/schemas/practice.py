from enum import StrEnum
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Citation

Difficulty = Literal["easy", "medium", "hard"]


class PracticeType(StrEnum):
    MCQ = "mcq"
    SHORT_ANSWER = "short_answer"
    CODE_TRACING = "code_tracing"


class PracticeRequest(BaseModel):
    course_id: int
    type: PracticeType
    topic: str | None = None
    source_id: str | None = None
    difficulty: Difficulty | None = None
    # "Bu eksik üzerine çalış": bu denemenin eksiklerine yönelik yeni soru.
    follow_up_of_attempt_id: int | None = None


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
