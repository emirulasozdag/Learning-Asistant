from app.retrieval.types import RetrievedPassage


def apply_video_time_prior(
    passages: list[RetrievedPassage], video_time_s: float
) -> list[RetrievedPassage]:
    """'Bu adım' soruları için durdurulan zamana yakın pasajlara yumuşak öncelik."""
    raise NotImplementedError
