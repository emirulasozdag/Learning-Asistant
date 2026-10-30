"""Kullanılabilirlik: System Usability Scale (SUS) ve genel memnuniyet (1–5).

SUS (Brooke, 1996): 10 madde, 1–5 Likert. Tek numaralı maddeler olumlu (katkı = cevap − 1), çift
numaralı maddeler olumsuz (katkı = 5 − cevap); toplam × 2,5 → 0–100. Madde metinleri ölçeğin
kullanılan (Türkçe uyarlaması dahil) sürümünden alınır; sıra ve kutup değiştirilmez.
"""

from collections.abc import Sequence
from statistics import mean

TARGET_SUS = 70
TARGET_SATISFACTION = 4.0
SUS_ITEMS = 10


def sus_respondent_score(answers: Sequence[int]) -> float:
    """Bir katılımcının SUS puanı (0–100)."""
    if len(answers) != SUS_ITEMS:
        raise ValueError(f"SUS: {SUS_ITEMS} madde gerekli, {len(answers)} geldi")
    if any(a not in (1, 2, 3, 4, 5) for a in answers):
        raise ValueError("SUS: cevaplar 1–5 olmalı")
    total = sum((a - 1) if index % 2 == 0 else (5 - a) for index, a in enumerate(answers))
    return total * 2.5


def sus_score(responses: Sequence[Sequence[int]]) -> float:
    """Katılımcı SUS puanlarının ortalaması. Eksik cevaplı form çağırandan önce ayıklanır."""
    if not responses:
        raise ValueError("sus_score: payda sıfır")
    return mean(sus_respondent_score(r) for r in responses)


def satisfaction_mean(ratings: Sequence[int]) -> float:
    """Genel memnuniyet maddesinin (1–5) ortalaması."""
    if not ratings:
        raise ValueError("satisfaction_mean: payda sıfır")
    if any(r not in (1, 2, 3, 4, 5) for r in ratings):
        raise ValueError("Memnuniyet 1–5 olmalı")
    return mean(ratings)
