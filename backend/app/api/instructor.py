from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.instructor import MistakeSummary, ReviewDecision

router = APIRouter(prefix="/instructor", tags=["instructor"])


@router.get("/courses/{course_id}/mistakes", response_model=list[MistakeSummary])
def frequent_mistakes(course_id: int) -> list[MistakeSummary]:
    """FR-16: sınıfın sık hataları (anonim, toplu)."""
    not_implemented("Eğitmen görünümü — sık hatalar")


@router.post("/reviews")
def submit_review(decision: ReviewDecision) -> None:
    """FR-16: eğitmen bir cevabı / pratik sorusunu onaylar veya düzeltir."""
    not_implemented("Eğitmen onayı / düzeltmesi")
