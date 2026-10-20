from collections.abc import Sequence

SUPPORTED = "supported"
UNSUPPORTED = "unsupported"
LABELS = (SUPPORTED, UNSUPPORTED)


def _check(claim_labels_per_answer: Sequence[Sequence[str]]) -> None:
    for labels in claim_labels_per_answer:
        invalid = [label for label in labels if label not in LABELS]
        if invalid:
            raise ValueError(f"İddia etiketi supported ya da unsupported olmalı: {invalid[:5]}")


def answers_with_unsupported_claim_rate(
    claim_labels_per_answer: Sequence[Sequence[str]],
) -> float:
    """En az bir 'unsupported' iddia içeren cevapların oranı (payda: etiketlenen cevaplar).

    İddiası olmayan cevap (ör. yalnızca kısa bir giriş cümlesi) paydada kalır, payda değil.
    """
    if not claim_labels_per_answer:
        raise ValueError("answers_with_unsupported_claim_rate: payda sıfır")
    _check(claim_labels_per_answer)
    flagged = sum(UNSUPPORTED in labels for labels in claim_labels_per_answer)
    return flagged / len(claim_labels_per_answer)


def unsupported_claim_rate(claim_labels_per_answer: Sequence[Sequence[str]]) -> float:
    """İddia düzeyinde: tüm iddialar içinde 'unsupported' olanların oranı (payda: iddia sayısı)."""
    _check(claim_labels_per_answer)
    claims = [label for labels in claim_labels_per_answer for label in labels]
    if not claims:
        raise ValueError("unsupported_claim_rate: payda sıfır")
    return claims.count(UNSUPPORTED) / len(claims)


TARGET_MAX = 0.10
