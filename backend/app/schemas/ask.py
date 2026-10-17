from pydantic import BaseModel, Field

from app.schemas.common import Citation


class AskRequest(BaseModel):
    """Grounded Q&A isteği. video_time_s: öğrencinin videoyu durdurduğu an (saniye)."""

    course_id: int
    question: str = Field(min_length=1)
    video_time_s: float | None = None
    conversation_id: int | None = None


class AskResponse(BaseModel):
    """Cite-or-decline cevabı: ya alıntılı cevap ya da gerekçeli reddetme."""

    answer: str | None
    citations: list[Citation] = []
    declined: bool = False
    decline_reason: str | None = None
    suggested_sources: list[Citation] = []
    conversation_id: int | None = None
