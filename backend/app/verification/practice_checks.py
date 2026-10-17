from app.retrieval.types import RetrievedPassage
from app.schemas.practice import PracticeItem


def check_key_in_options(item: PracticeItem) -> bool:
    """MCQ: doğru cevap seçenekler arasında mı?"""
    raise NotImplementedError


def check_distinct_distractors(item: PracticeItem) -> bool:
    """MCQ: çeldiriciler birbirinden ve cevaptan farklı mı?"""
    raise NotImplementedError


def check_resolve_agreement(item: PracticeItem, passage: RetrievedPassage) -> bool:
    """Soru kaynaktan yeniden çözüldüğünde aynı cevap çıkıyor mu?"""
    raise NotImplementedError


def passes_all_checks(item: PracticeItem, passage: RetrievedPassage) -> bool:
    """Kontrollerden geçmeyen soru öğrenciye gösterilmez."""
    raise NotImplementedError
