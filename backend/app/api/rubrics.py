from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.rubrics import Rubric, RubricIn

router = APIRouter(prefix="/instructor/courses/{course_id}/rubrics", tags=["instructor"])


@router.get("", response_model=list[Rubric])
def list_rubrics(course_id: int) -> list[Rubric]:
    """FR-13: dersin rubrikleri ve referans cevapları."""
    not_implemented("Rubrik listesi")


@router.post("", response_model=Rubric)
def create_rubric(course_id: int, rubric: RubricIn) -> Rubric:
    """FR-13: eğitmen rubrik + referans cevap girer."""
    not_implemented("Rubrik girişi")
