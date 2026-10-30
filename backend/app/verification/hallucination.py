"""Hallucination oranı: judge'ın desteklenmeyen bulduğu iddia içeren cevapların oranı (FR-14).

Kaynak: kaydedilen asistan mesajlarının meta'sındaki iddia kontrolü (`qa/service.answer_meta`).
Desteklenmeyen iddialar öğrenciye gösterilmeden çıkarılır; oran, üreticinin ne sıklıkla
desteksiz iddia yazdığını ölçer (gösterilen cevabın değil, ham üretimin oranı).
"""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Message


@dataclass(frozen=True)
class HallucinationStats:
    checked_answers: int
    answers_with_unsupported: int
    claims: int
    unsupported_claims: int
    # Kontrol edilemeyen (judge yok / hata) cevaplar; orana girmez, ayrıca raporlanır.
    unchecked_answers: int

    @property
    def answer_rate(self) -> float | None:
        if not self.checked_answers:
            return None
        return self.answers_with_unsupported / self.checked_answers

    @property
    def claim_rate(self) -> float | None:
        return self.unsupported_claims / self.claims if self.claims else None


def summarize(metas: Iterable[dict]) -> HallucinationStats:
    checked = with_unsupported = claims = unsupported = unchecked = 0
    for meta in metas:
        check = (meta or {}).get("claim_check")
        if not check:
            continue
        if check.get("status") != "checked":
            if check.get("status") in ("failed", "not_configured"):
                unchecked += 1
            continue
        checked += 1
        claims += int(check.get("claims", 0))
        count = int(check.get("unsupported", 0))
        unsupported += count
        with_unsupported += count > 0
    return HallucinationStats(checked, with_unsupported, claims, unsupported, unchecked)


def hallucination_rate(db: Session, course_id: int) -> HallucinationStats:
    """Dersin kayıtlı cevapları üzerinden oranlar."""
    metas = db.scalars(
        select(Message.meta)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.course_id == course_id, Message.role == "assistant")
    )
    return summarize(meta for meta in metas if meta)
