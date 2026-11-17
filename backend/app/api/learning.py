from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.auth.dependencies import AuthUser
from app.learning.record import get_learning_record as build_learning_record
from app.schemas.learning import LearningRecord

router = APIRouter(prefix="/courses/{course_id}/learning-record", tags=["learning"])


@router.get("", response_model=LearningRecord)
def get_learning_record(course_id: int, user: AuthUser, db: DbSession) -> LearningRecord:
    """FR-15: öğrencinin bu dersteki kendi öğrenme kaydı.

    Yalnızca araştırma kaydı açıkken yapılan denemeler girer (ADR-4); kayıt kapalıysa
    `logging_enabled=false` döner. Kimse başkasının kaydını göremez.
    """
    get_course_for(db, user, course_id)
    return build_learning_record(db, user.user, course_id)
