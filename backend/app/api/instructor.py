from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.auth.dependencies import AuthUser, not_found_error, require_course_role
from app.instructor.activity import course_activity
from app.instructor.mistakes import frequent_mistakes as build_frequent_mistakes
from app.instructor.review import apply_review, resolve_target
from app.schemas.instructor import CourseActivity, MistakeSummary, ReviewDecision, ReviewOut

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
    """FR-16: sınıfın sık hataları (anonim, toplu; en az üç öğrencide görülenler)."""
    get_course_for(db, user, course_id, "instructor", "ta")
    return build_frequent_mistakes(db, course_id)


@router.post("/reviews", response_model=ReviewOut)
def submit_review(decision: ReviewDecision, user: AuthUser, db: DbSession) -> ReviewOut:
    """FR-16: eğitmen bir asistan cevabını / pratik sorusunu onaylar veya düzeltir.

    Hedefin dersi hedeften çözülür. Hedef yoksa, incelenemezse ya da kullanıcı o dersin
    üyesi değilse 404 (varlık sızdırılmaz); üye ama eğitmen değilse 403.
    """
    code = (
        "practice_item_not_found"
        if decision.target_type == "practice_item"
        else ("message_not_found")
    )
    target = resolve_target(db, decision)
    if target is None:
        raise not_found_error(code)
    require_course_role(user, target.course_id, "instructor", not_found=code)
    return apply_review(db, user.user, decision, target)
