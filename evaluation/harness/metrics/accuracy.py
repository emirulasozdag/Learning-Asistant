from collections.abc import Sequence

SCORES = (0, 1, 2)


def fully_correct_rate(scores: Sequence[int]) -> float:
    """Eğitmen referansına göre verilen 0/1/2 puanlarında 2 olanların oranı.

    0 = yanlış ya da cevap yok, 1 = kısmen doğru / eksik, 2 = tamamen doğru. Payda, puanlanan
    cevap sayısıdır; reddedilen cevaplanabilir soruları 0 olarak eklemek çağıranın işidir.
    """
    if not scores:
        raise ValueError("fully_correct_rate: payda sıfır")
    invalid = [score for score in scores if score not in SCORES]
    if invalid:
        raise ValueError(f"Puan 0, 1 ya da 2 olmalı: {invalid[:5]}")
    return sum(score == 2 for score in scores) / len(scores)


TARGET = 0.80
