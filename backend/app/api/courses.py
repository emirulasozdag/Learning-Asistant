from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.courses import CourseSummary

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseSummary])
def list_courses() -> list[CourseSummary]:
    """Kullanıcının dersleri; öğrenci ders seçerek başlar."""
    not_implemented("Ders listesi")
