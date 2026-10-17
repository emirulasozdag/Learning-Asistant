from app.retrieval.types import RetrievedPassage


def lexical_search(course_id: int, query: str, k: int) -> list[RetrievedPassage]:
    """PostgreSQL full-text search; ders filtresi aramadan önce uygulanır."""
    raise NotImplementedError
