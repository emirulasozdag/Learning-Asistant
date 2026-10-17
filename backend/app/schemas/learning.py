from pydantic import BaseModel


class AttemptSummary(BaseModel):
    item_id: int
    concept: str | None = None
    score: float
    max_score: float


class LearningRecord(BaseModel):
    course_id: int
    attempts: list[AttemptSummary] = []
