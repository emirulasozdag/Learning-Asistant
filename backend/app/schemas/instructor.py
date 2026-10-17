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
