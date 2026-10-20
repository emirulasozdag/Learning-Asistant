from collections.abc import Sequence


def _rate(flags: Sequence[bool], label: str) -> float:
    if not flags:
        raise ValueError(f"{label}: payda sıfır")
    return sum(flags) / len(flags)


def decline_rate(out_of_scope_declined: Sequence[bool]) -> float:
    """Kapsam dışı sorularda doğru reddetme oranı (hedef: 30 soru)."""
    return _rate(out_of_scope_declined, "decline_rate")


def over_refusal_rate(answerable_declined: Sequence[bool]) -> float:
    """Cevaplanabilir sorularda gereksiz reddetme oranı."""
    return _rate(answerable_declined, "over_refusal_rate")


TARGET_DECLINE = 0.90
TARGET_OVER_REFUSAL_MAX = 0.10
