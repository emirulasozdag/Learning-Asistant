"""Alıntı kapsamı: cevabın gösterdiği kaynaklar, eğitmenin işaretlediği kanıtı ne kadar karşılıyor.

ALCE'deki alıntı recall/precision fikrinin gold kanıt konumlarıyla ölçülen hali. İddia düzeyinde
"bu iddia alıntısıyla destekleniyor mu" sorusu hallucination metriğinin (judge/insan) işidir.
"""

from collections.abc import Callable, Sequence


def evidence_coverage[T, G](
    cited: Sequence[Sequence[T]],
    gold: Sequence[Sequence[G]],
    match: Callable[[G, T], bool] = lambda g, c: g == c,
) -> float:
    """Soru başına: alıntılarla karşılanan gold kanıtların oranı; sorular üzerinden ortalama.

    Gold kanıtı olmayan sorular hesaba katılmaz; hiç soru kalmazsa ValueError.
    """
    if len(cited) != len(gold):
        raise ValueError("cited ve gold aynı uzunlukta olmalı")
    per_question = [
        sum(any(match(g, c) for c in citations) for g in evidence) / len(evidence)
        for citations, evidence in zip(cited, gold, strict=True)
        if evidence
    ]
    if not per_question:
        raise ValueError("Gold kanıtı olan soru yok")
    return sum(per_question) / len(per_question)


def precision_counts[T, G](
    cited: Sequence[Sequence[T]],
    gold: Sequence[Sequence[G]],
    match: Callable[[G, T], bool] = lambda g, c: g == c,
) -> tuple[int, int]:
    """(gold kanıta düşen alıntı sayısı, toplam alıntı) — gold kanıtı olan sorular üzerinden."""
    if len(cited) != len(gold):
        raise ValueError("cited ve gold aynı uzunlukta olmalı")
    hits = total = 0
    for citations, evidence in zip(cited, gold, strict=True):
        if not evidence:
            continue
        total += len(citations)
        hits += sum(any(match(g, c) for g in evidence) for c in citations)
    return hits, total
