from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.api.not_implemented import not_implemented
from app.auth.dependencies import AuthUser
from app.schemas.learning import LearningRecord

router = APIRouter(prefix="/courses/{course_id}/learning-record", tags=["learning"])


@router.get("", response_model=LearningRecord)
def get_learning_record(course_id: int, user: AuthUser, db: DbSession) -> LearningRecord:
    """FR-15: öğrencinin kendi öğrenme kaydı (opt-in)."""
    get_course_for(db, user, course_id)
    not_implemented("Öğrenme kaydı")
