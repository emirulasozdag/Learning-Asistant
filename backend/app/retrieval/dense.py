from app.retrieval.types import RetrievedPassage


def dense_search(course_id: int, query: str, k: int) -> list[RetrievedPassage]:
    """multilingual-e5 embedding + pgvector; ders filtresi aramadan önce uygulanır."""
    raise NotImplementedError
