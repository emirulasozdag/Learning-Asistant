from app.retrieval.types import RetrievedPassage


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedPassage]], k: int = 60
) -> list[RetrievedPassage]:
    """Dense ve lexical sıralamaları RRF ile birleştir."""
    raise NotImplementedError
