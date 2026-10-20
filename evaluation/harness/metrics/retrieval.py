from collections.abc import Callable, Sequence


def recall_at_k[T, G](
    retrieved: Sequence[Sequence[T]],
    gold: Sequence[Sequence[G]],
    k: int = 5,
    match: Callable[[G, T], bool] = lambda g, r: g == r,
) -> float:
    """Gold kanıt pasajlarına göre Recall@k (sorular üzerinden ortalama).

    Her soru için: ilk k sonuçta en az bir eşleşmesi bulunan gold kanıtların oranı.
    Gold kanıtı olmayan sorular hesaba katılmaz; hiç soru kalmazsa ValueError.
    """
    if len(retrieved) != len(gold):
        raise ValueError("retrieved ve gold aynı uzunlukta olmalı")
    if k < 1:
        raise ValueError("k en az 1 olmalı")
    per_question = [
        sum(any(match(g, r) for r in hits[:k]) for g in evidence) / len(evidence)
        for hits, evidence in zip(retrieved, gold, strict=True)
        if evidence
    ]
    if not per_question:
        raise ValueError("Gold kanıtı olan soru yok")
    return sum(per_question) / len(per_question)


TARGET = 0.85
