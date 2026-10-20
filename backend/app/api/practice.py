from fastapi import APIRouter

from app.api.deps import DbSession, get_course_for
from app.api.not_implemented import not_implemented
from app.auth.dependencies import AuthUser, require_consent
from app.schemas.evaluation import AnswerFeedback, AnswerSubmission
from app.schemas.practice import PracticeItem, PracticeRequest

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("", response_model=PracticeItem)
def generate_practice(request: PracticeRequest, user: AuthUser, db: DbSession) -> PracticeItem:
    """FR-11..12: kaynak pasajdan pratik sorusu üret, otomatik kontrollerden geçir."""
    get_course_for(db, user, request.course_id)
    require_consent(user)
    not_implemented("Pratik soru üretimi")


@router.post("/{item_id}/answer", response_model=AnswerFeedback)
def submit_answer(item_id: int, submission: AnswerSubmission, user: AuthUser) -> AnswerFeedback:
    """FR-13: rubrik + referans cevapla değerlendir, eksikleri açıkla, takip sorusu öner.

    Uygulanınca sorunun dersi `item_id`'den çözülür ve üyelik denetlenir (#15).
    """
    not_implemented("Cevap değerlendirme")
