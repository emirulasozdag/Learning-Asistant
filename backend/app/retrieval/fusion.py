from dataclasses import replace

from app.retrieval.types import RetrievedPassage

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: list[list[RetrievedPassage]],
    k: int = RRF_K,
    weights: list[float] | None = None,
) -> list[RetrievedPassage]:
    """Sıralamaları RRF ile birleştirir: skor = Σ ağırlık / (k + sıra).

    Aynı parça birden çok listede varsa bilgileri (anlamsal skor, kelime sırası) birleşir;
    ilk listelerdeki değerler önceliklidir.
    """
    weights = weights or [1.0] * len(rankings)
    merged: dict[str, RetrievedPassage] = {}
    for ranking, weight in zip(rankings, weights, strict=True):
        for rank, passage in enumerate(ranking, start=1):
            contribution = weight / (k + rank)
            current = merged.get(passage.source_id)
            if current is None:
                merged[passage.source_id] = replace(passage, score=contribution)
                continue
            merged[passage.source_id] = replace(
                current,
                score=current.score + contribution,
                dense_score=current.dense_score
                if current.dense_score is not None
                else passage.dense_score,
                lexical_rank=current.lexical_rank
                if current.lexical_rank is not None
                else passage.lexical_rank,
            )
    return sorted(merged.values(), key=lambda p: (-p.score, int(p.source_id)))
