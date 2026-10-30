"""Pratik sorusu kabul oranı: eğitmen / TA incelemesinde kabul edilebilir bulunan soruların payı."""

from collections.abc import Sequence

TARGET = 0.85


def acceptable_rate(reviewer_verdicts: Sequence[bool]) -> float:
    """Kabul edilebilir (doğru, kaynağa dayalı, öğretici) bulunan soruların oranı (40 soru)."""
    if not reviewer_verdicts:
        raise ValueError("acceptable_rate: payda sıfır")
    return sum(bool(v) for v in reviewer_verdicts) / len(reviewer_verdicts)
