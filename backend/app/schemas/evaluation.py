from pydantic import BaseModel, Field

from app.schemas.common import Citation


class AnswerSubmission(BaseModel):
    answer: str = Field(min_length=1)


class AnswerFeedback(BaseModel):
    """Rubrik tabanlı formatif geri bildirim (resmî not değildir)."""

    score: float
    max_score: float
    missing_concepts: list[str] = []
    explanation: str
    citations: list[Citation] = []
    follow_up_item_id: int | None = None
