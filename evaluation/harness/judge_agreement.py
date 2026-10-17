def cohen_kappa(judge_labels: list[str], human_labels: list[str]) -> float:
    """Judge–insan uyumu. Judge'a ancak κ ≥ 0,6 ise güvenilir."""
    raise NotImplementedError


KAPPA_THRESHOLD = 0.6
