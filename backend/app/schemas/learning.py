from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import Citation
from app.schemas.practice import PracticeType


class AttemptSummary(BaseModel):
    """Öğrencinin bir pratik denemesi (formatif; resmî not değildir)."""

    item_id: int
    attempt_id: int
    type: PracticeType
    concept: str | None = None
    score: float
    max_score: float
    # Değerlendiricinin bu denemede eksik bulduğu kavramlar.
    missing_concepts: list[str] = []
    attempted_at: datetime
    # Soru sonradan eğitmen tarafından geri çekildiyse (düzeltildiyse).
    withdrawn: bool = False


class ConceptProgress(BaseModel):
    """Bir kavramdaki ilerleme: denemeler en yeniden eskiye özetlenir."""

    concept: str
    attempts: int
    # Puan oranları 0..1 (puan / en yüksek puan).
    last_score_ratio: float
    best_score_ratio: float
    # Son denemede hâlâ eksik görünen kavramlar; boşsa son deneme tam.
    open_gaps: list[str] = []
    # Konunun ders materyalindeki yeri (son denemenin sorusu).
    source: Citation | None = None


class LearningRecord(BaseModel):
    """Öğrencinin kendi öğrenme kaydı (FR-15, ADR-4).

    Yalnızca araştırma kaydı açıkken yapılan denemeler girer. `logging_enabled` kaydın şu an
    açık olup olmadığını söyler; kapalıysa yeni denemeler kayda yazılmaz.
    """

    course_id: int
    logging_enabled: bool = False
    attempts: list[AttemptSummary] = []
    concepts: list[ConceptProgress] = []
