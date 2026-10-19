from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


class MistakeSummary(BaseModel):
    """Sınıfın sık yaptığı hata: hangi kavram, hangi hata, hangi kaynak düzeltti."""

    concept: str
    error_type: str
    count: int
    fixing_source_ids: list[str] = []


class ReviewDecision(BaseModel):
    """Eğitmenin bir asistan cevabını veya pratik sorusunu onaylaması / düzeltmesi."""

    target_type: Literal["message", "practice_item"]
    target_id: int
    decision: Literal["approve", "correct"]
    correction: str | None = None


class DailyCount(BaseModel):
    day: date
    questions: int


class SourceUsage(BaseModel):
    """Cevaplarda en çok alıntılanan ders sayfaları."""

    source_id: str
    document_title: str
    page: int | None = None
    citations: int


class QuestionItem(BaseModel):
    question: str
    # answered | insufficient_evidence | unsupported | model_refusal | provider_failure
    outcome: str
    asked_at: datetime


class CourseActivity(BaseModel):
    """Dersin soru-cevap etkinliği: anonim, ders düzeyinde, kayıtlı mesajlardan hesaplanır."""

    questions: int
    conversations: int
    answered: int
    # Materyalde yeterli dayanak yok (alakasızlık kapısı ya da model "YOK:" dedi).
    not_covered: int
    # Doğrulanamadı ya da model reddetti.
    not_generated: int
    # Modele ulaşılamadı; ilgili bölüm alıntılandı.
    unavailable: int
    daily: list[DailyCount]
    top_sources: list[SourceUsage]
    recent_questions: list[QuestionItem]
    # Materyalin yetmediği sorular: eğitmen için "neyi eklemeliyim" listesi.
    unanswered_questions: list[QuestionItem]
