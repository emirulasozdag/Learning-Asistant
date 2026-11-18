from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.auth.dependencies import AuthUser
from app.instructor import rubrics
from app.schemas.rubrics import Rubric, RubricIn

router = APIRouter(prefix="/instructor/courses/{course_id}/rubrics", tags=["instructor"])


@router.get("", response_model=list[Rubric])
def list_rubrics(course_id: int, user: AuthUser, db: DbSession) -> list[Rubric]:
    """FR-13: dersin rubrikleri ve referans cevapları (en yeniler önce, en fazla 100)."""
    get_course_for(db, user, course_id, "instructor", "ta")
    return rubrics.list_rubrics(db, course_id)


@router.post("", response_model=Rubric)
def create_rubric(course_id: int, rubric: RubricIn, user: AuthUser, db: DbSession) -> Rubric:
    """FR-13: eğitmen rubrik + referans cevap girer; soruya bağlıysa üretilmiş rubriğin yerine
    geçer ve onaylıdır. Soru bu derste yoksa 404, çoktan seçmeliyse ya da kaynak bu dersin
    değilse 422."""
    get_course_for(db, user, course_id, "instructor")
    return rubrics.create_rubric(db, course_id, user.user, rubric)
