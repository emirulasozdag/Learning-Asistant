from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Citation


class AnswerSubmission(BaseModel):
    """Öğrencinin cevabı: tam biri dolu olur (short_answer/code_tracing → metin, mcq → seçenek)."""

    answer_text: str | None = Field(default=None, min_length=1)
    # `PracticeItem.options` içindeki sıra (0'dan başlar).
    selected_option: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def exactly_one_answer(self) -> Self:
        if (self.answer_text is None) == (self.selected_option is None):
            raise ValueError("answer_text ve selected_option'dan tam biri verilmeli")
        return self


class CriterionScore(BaseModel):
    description: str
    awarded: float
    points: float
    rationale: str = ""


class AnswerFeedback(BaseModel):
    """Rubrik tabanlı formatif geri bildirim (resmî not değildir).

    Cevap anahtarı ve referans cevap ancak cevap gönderildikten sonra, bu yanıtta döner.
    """

    attempt_id: int
    item_id: int
    score: float
    max_score: float
    understood: list[str] = []
    missing_concepts: list[str] = []
    explanation: str
    citations: list[Citation] = []
    follow_up_item_id: int | None = None
    # [ekleme] MCQ'da doğru şık; açık uçlu sorularda örnek tam puanlık cevap ve ölçüt puanları.
    correct_option: int | None = None
    reference_answer: str | None = None
    criteria: list[CriterionScore] = []
