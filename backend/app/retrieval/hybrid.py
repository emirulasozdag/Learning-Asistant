from app.retrieval.types import RetrievedPassage


def retrieve(
    course_id: int, query: str, video_time_s: float | None = None, k: int = 5
) -> list[RetrievedPassage]:
    """dense + lexical → RRF → (video-zaman önceliği) → rerank."""
    raise NotImplementedError
