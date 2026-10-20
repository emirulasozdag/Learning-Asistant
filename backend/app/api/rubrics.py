from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.api.not_implemented import not_implemented
from app.auth.dependencies import AuthUser
from app.schemas.rubrics import Rubric, RubricIn

router = APIRouter(prefix="/instructor/courses/{course_id}/rubrics", tags=["instructor"])


@router.get("", response_model=list[Rubric])
def list_rubrics(course_id: int, user: AuthUser, db: DbSession) -> list[Rubric]:
    """FR-13: dersin rubrikleri ve referans cevapları."""
    get_course_for(db, user, course_id, "instructor", "ta")
    not_implemented("Rubrik listesi")


@router.post("", response_model=Rubric)
def create_rubric(course_id: int, rubric: RubricIn, user: AuthUser, db: DbSession) -> Rubric:
    """FR-13: eğitmen rubrik + referans cevap girer."""
    get_course_for(db, user, course_id, "instructor")
    not_implemented("Rubrik girişi")
