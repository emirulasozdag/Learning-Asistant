from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.api.not_implemented import not_implemented
from app.auth.dependencies import AuthUser
from app.instructor.activity import course_activity
from app.schemas.instructor import CourseActivity, MistakeSummary, ReviewDecision

router = APIRouter(prefix="/instructor", tags=["instructor"])


@router.get("/courses/{course_id}/activity", response_model=CourseActivity)
def activity(course_id: int, user: AuthUser, db: DbSession) -> CourseActivity:
    """Dersin soru-cevap etkinliği: sayılar, son 14 gün, en çok alıntılanan kaynaklar ve
    materyalde cevabı bulunamayan sorular. Yalnızca araştırma kaydını açan öğrencilerin
    kayıtlı mesajlarından, toplu ve anonim hesaplanır (ADR-4)."""
    get_course_for(db, user, course_id, "instructor", "ta")
    return course_activity(db, course_id)


@router.get("/courses/{course_id}/mistakes", response_model=list[MistakeSummary])
def frequent_mistakes(course_id: int, user: AuthUser, db: DbSession) -> list[MistakeSummary]:
    """FR-16: sınıfın sık hataları (anonim, toplu)."""
    get_course_for(db, user, course_id, "instructor", "ta")
    not_implemented("Eğitmen görünümü — sık hatalar")


@router.post("/reviews")
def submit_review(decision: ReviewDecision, user: AuthUser) -> None:
    """FR-16: eğitmen bir cevabı / pratik sorusunu onaylar veya düzeltir.

    Hedefin dersi uygulanınca hedeften çözülür ve eğitmen rolü denetlenir.
    """
    not_implemented("Eğitmen onayı / düzeltmesi")
