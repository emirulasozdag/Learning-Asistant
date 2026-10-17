from app.retrieval.types import RetrievedPassage


def rerank(query: str, passages: list[RetrievedPassage], top_k: int) -> list[RetrievedPassage]:
    """Opsiyonel cross-encoder reranker (top-k precision)."""
    raise NotImplementedError
