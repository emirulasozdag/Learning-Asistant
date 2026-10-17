from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.learning import LearningRecord

router = APIRouter(prefix="/courses/{course_id}/learning-record", tags=["learning"])


@router.get("", response_model=LearningRecord)
def get_learning_record(course_id: int) -> LearningRecord:
    """FR-15: öğrencinin kendi öğrenme kaydı (opt-in)."""
    not_implemented("Öğrenme kaydı")
