from fastapi import APIRouter

from app.api.deps import DbSession, get_course_or_404
from app.api.not_implemented import not_implemented
from app.instructor.activity import course_activity
from app.schemas.instructor import CourseActivity, MistakeSummary, ReviewDecision

router = APIRouter(prefix="/instructor", tags=["instructor"])


@router.get("/courses/{course_id}/activity", response_model=CourseActivity)
def activity(course_id: int, db: DbSession) -> CourseActivity:
    """Dersin soru-cevap etkinliği: sayılar, son 14 gün, en çok alıntılanan kaynaklar ve
    materyalde cevabı bulunamayan sorular. Kayıtlı mesajlardan hesaplanır."""
    get_course_or_404(db, course_id)
    return course_activity(db, course_id)


@router.get("/courses/{course_id}/mistakes", response_model=list[MistakeSummary])
def frequent_mistakes(course_id: int) -> list[MistakeSummary]:
    """FR-16: sınıfın sık hataları (anonim, toplu)."""
    not_implemented("Eğitmen görünümü — sık hatalar")


@router.post("/reviews")
def submit_review(decision: ReviewDecision) -> None:
    """FR-16: eğitmen bir cevabı / pratik sorusunu onaylar veya düzeltir."""
    not_implemented("Eğitmen onayı / düzeltmesi")
