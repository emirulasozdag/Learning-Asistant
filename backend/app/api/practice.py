from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.evaluation import AnswerFeedback, AnswerSubmission
from app.schemas.practice import PracticeItem, PracticeRequest

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("", response_model=PracticeItem)
def generate_practice(request: PracticeRequest) -> PracticeItem:
    """FR-11..12: kaynak pasajdan pratik sorusu üret, otomatik kontrollerden geçir."""
    not_implemented("Pratik soru üretimi")


@router.post("/{item_id}/answer", response_model=AnswerFeedback)
def submit_answer(item_id: int, submission: AnswerSubmission) -> AnswerFeedback:
    """FR-13: rubrik + referans cevapla değerlendir, eksikleri açıkla, takip sorusu öner."""
    not_implemented("Cevap değerlendirme")
