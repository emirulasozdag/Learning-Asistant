def decline_rate(out_of_scope_declined: list[bool]) -> float:
    """30 kapsam dışı soruda doğru reddetme oranı."""
    raise NotImplementedError


def over_refusal_rate(answerable_declined: list[bool]) -> float:
    """Cevaplanabilir sorularda gereksiz reddetme oranı."""
    raise NotImplementedError


TARGET_DECLINE = 0.90
TARGET_OVER_REFUSAL_MAX = 0.10
