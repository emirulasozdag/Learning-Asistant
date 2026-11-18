from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.schemas.ask import AskOutcome
from app.schemas.common import Citation
from app.schemas.practice import Difficulty, PracticeType

# Eğitmen düzeltmesinin en uzun hali (karakter).
MAX_CORRECTION = 4000


class MistakeSummary(BaseModel):
    """Sınıfın sık yaptığı hata: hangi kavram, hangi hata, hangi kaynak düzeltir (#20).

    Yalnızca araştırma kaydını açmış öğrencilerin denemelerinden, toplu hesaplanır; en az
    üç farklı öğrencide görülmeyen hata gösterilmez (ADR-4).
    """

    concept: str
    # "wrong_option": çoktan seçmelide yanlış şık; "missing_concept": açık uçlu cevapta eksik.
    error_type: Literal["wrong_option", "missing_concept"]
    # Hatanın görüldüğü deneme sayısı.
    count: int
    # Hatayı yapan farklı öğrenci sayısı.
    students: int = 0
    fixing_source_ids: list[str] = []


class ReviewDecision(BaseModel):
    """Eğitmenin bir asistan cevabını veya pratik sorusunu onaylaması / düzeltmesi."""

    target_type: Literal["message", "practice_item"]
    target_id: int
    decision: Literal["approve", "correct"]
    # "correct" kararında zorunlu: neyin yanlış olduğu ve doğrusu.
    correction: str | None = Field(default=None, max_length=MAX_CORRECTION)

    @model_validator(mode="after")
    def correction_required_for_correct(self) -> Self:
        if self.correction is not None:
            self.correction = self.correction.strip() or None
        if self.decision == "correct" and self.correction is None:
            raise ValueError("Düzeltme kararında düzeltme metni yazılmalı")
        return self


class LatestReview(BaseModel):
    decision: Literal["approve", "correct"]
    correction: str | None = None
    created_at: datetime


class PracticeItemReview(BaseModel):
    """Eğitmenin incelediği pratik sorusu (#22): cevap anahtarı ve açıklama dahil.

    Öğrenci kimliği ve deneme bilgisi içermez; soru dersin malıdır.
    """

    id: int
    type: PracticeType
    topic: str | None = None
    difficulty: Difficulty
    prompt: str
    options: list[str] | None = None
    correct_option: int | None = None
    reference_answer: str | None = None
    explanation: str
    # "released": öğrencilere sunuluyor; "withdrawn": eğitmen düzeltti, sunulmuyor.
    status: Literal["released", "withdrawn"]
    rubric_approved: bool = False
    source: Citation
    created_at: datetime
    latest_review: LatestReview | None = None


class ReviewOut(BaseModel):
    """Kaydedilen eğitmen kararı."""

    id: int
    target_type: Literal["message", "practice_item"]
    target_id: int
    decision: Literal["approve", "correct"]
    correction: str | None = None
    created_at: datetime


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
    outcome: AskOutcome
    asked_at: datetime
    # Asistanın bu soruya cevabı: eğitmen onay/düzeltme için hedef olarak kullanır (#20).
    answer_message_id: int | None = None


class CourseActivity(BaseModel):
    """Dersin soru-cevap etkinliği: anonim, ders düzeyinde, kayıtlı mesajlardan hesaplanır."""

    questions: int
    conversations: int
    answered: int
    # Materyalde yeterli dayanak yok (alakasızlık kapısı ya da model "YOK:" dedi).
    not_covered: int
    # Doğrulanamadı ya da model reddetti.
    not_generated: int
    # Modele ulaşılamadı ya da cevap kontrol edilemedi (#10); ilgili bölüm alıntılandı.
    unavailable: int
    daily: list[DailyCount]
    top_sources: list[SourceUsage]
    recent_questions: list[QuestionItem]
    # Materyalin yetmediği sorular: eğitmen için "neyi eklemeliyim" listesi.
    unanswered_questions: list[QuestionItem]
