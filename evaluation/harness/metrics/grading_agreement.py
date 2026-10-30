"""Asistan puanı ile eğitmen/TA puanı arasındaki uyum: quadratic weighted kappa (QWK)."""

from collections.abc import Sequence

TARGET = 0.70


def quadratic_weighted_kappa(
    assistant_scores: Sequence[int],
    instructor_scores: Sequence[int],
    min_score: int | None = None,
    max_score: int | None = None,
) -> float:
    """Aynı cevaplara verilen iki tam sayı puan dizisi arasındaki QWK (Cohen, ağırlık (i-j)²).

    Puan aralığı verilmezse iki dizinin en küçük/en büyük değerinden alınır; rubrikte tanımlı
    aralık bilinirse verilmelidir (ör. 0–4), aksi halde hiç kullanılmayan uç puanlar hesaba girmez.
    Beklenen uyumsuzluk sıfırsa (herkes aynı puanı verdi) κ tanımsızdır: ValueError.
    """
    if len(assistant_scores) != len(instructor_scores):
        raise ValueError("QWK: iki puan dizisi aynı uzunlukta olmalı")
    if not assistant_scores:
        raise ValueError("QWK: payda sıfır")
    values = [*assistant_scores, *instructor_scores]
    if any(int(v) != v for v in values):
        raise ValueError("QWK: puanlar tam sayı olmalı")
    low = min(values) if min_score is None else min_score
    high = max(values) if max_score is None else max_score
    if min(values) < low or max(values) > high:
        raise ValueError(f"QWK: puanlar {low}–{high} aralığı dışında")
    size = high - low + 1
    if size < 2:
        raise ValueError("QWK: en az iki puan düzeyi gerekli")

    observed = [[0.0] * size for _ in range(size)]
    for a, b in zip(assistant_scores, instructor_scores, strict=True):
        observed[int(a) - low][int(b) - low] += 1
    n = len(assistant_scores)
    row = [sum(observed[i]) for i in range(size)]
    col = [sum(observed[i][j] for i in range(size)) for j in range(size)]

    numerator = denominator = 0.0
    for i in range(size):
        for j in range(size):
            weight = (i - j) ** 2 / (size - 1) ** 2
            numerator += weight * observed[i][j]
            denominator += weight * row[i] * col[j] / n
    if denominator == 0:
        raise ValueError("QWK: beklenen uyumsuzluk sıfır (tüm puanlar aynı); κ tanımsız")
    return 1.0 - numerator / denominator
