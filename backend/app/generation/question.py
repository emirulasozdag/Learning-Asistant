from app.retrieval.types import RetrievedPassage
from app.schemas.practice import PracticeItem, PracticeType


def generate_practice_item(passage: RetrievedPassage, item_type: PracticeType) -> PracticeItem:
    """Tek pasajdan MCQ / kısa cevap / code tracing sorusu + açıklama üret."""
    raise NotImplementedError
