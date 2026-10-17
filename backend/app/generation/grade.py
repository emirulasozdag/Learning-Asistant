from app.schemas.evaluation import AnswerFeedback
from app.schemas.practice import PracticeItem


def grade_answer(item: PracticeItem, answer: str) -> AnswerFeedback:
    """Referans cevap + rubrik getir → skor, eksik kavramlar, alıntılı açıklama, takip."""
    raise NotImplementedError
