from app.verification.judge import ClaimLabel


def log_claim_checks(message_id: int, labels: list[ClaimLabel]) -> None:
    """Supported / unsupported sonuçlarını kaydet."""
    raise NotImplementedError


def hallucination_rate(course_id: int) -> float:
    """Desteklenmeyen iddia içeren cevapların oranı."""
    raise NotImplementedError
