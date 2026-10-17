from pydantic import BaseModel, Field


class RubricCriterion(BaseModel):
    description: str
    points: float = Field(gt=0)


class RubricIn(BaseModel):
    """Eğitmenin girdiği rubrik + referans cevap. Bir soruya veya bir kavrama bağlanır."""

    concept: str
    reference_answer: str
    criteria: list[RubricCriterion] = Field(min_length=1)
    practice_item_id: int | None = None
    source_ids: list[str] = []


class Rubric(RubricIn):
    id: int
    course_id: int
    approved: bool = False
