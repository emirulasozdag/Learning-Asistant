"""Embedding ve RRF birleştirme (veritabanı gerektirmez)."""

import math

from app.embeddings.fake import FakeEmbedder
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.types import RetrievedPassage


def passage(source_id: str, dense: float | None = None, lexical: int | None = None):
    return RetrievedPassage(
        source_id=source_id,
        document_id=1,
        document_title="Notlar",
        text="",
        score=0.0,
        dense_score=dense,
        lexical_rank=lexical,
    )


def test_rrf_rewards_passages_found_by_both_methods() -> None:
    dense = [passage("1", dense=0.9), passage("2", dense=0.8), passage("3", dense=0.7)]
    lexical = [passage("3", lexical=1), passage("4", lexical=2)]

    fused = reciprocal_rank_fusion([dense, lexical])

    assert [p.source_id for p in fused][:2] == ["3", "1"]
    best = fused[0]
    assert (best.dense_score, best.lexical_rank) == (0.7, 1)
    assert math.isclose(best.score, 1 / 63 + 1 / 61)


def test_rrf_keeps_single_method_hits_and_is_deterministic() -> None:
    fused = reciprocal_rank_fusion([[passage("5", dense=0.6)], [passage("2", lexical=1)]])

    assert [p.source_id for p in fused] == ["2", "5"]  # eşit skor → küçük id önce


def test_fake_embedder_is_unit_length_and_similar_for_shared_words() -> None:
    embedder = FakeEmbedder()
    a, b, c = embedder.embed_passages(["ikili arama sirali dizi", "sirali dizide ikili arama", "x"])

    def cosine(u, v):
        return sum(x * y for x, y in zip(u, v, strict=True))

    assert len(a) == embedder.dim
    assert math.isclose(cosine(a, a), 1.0, rel_tol=1e-9)
    assert cosine(a, b) > cosine(a, c)


def test_rrf_weights_favour_the_current_question() -> None:
    current = [passage("4", dense=0.86)]
    context = [passage("2", dense=0.88)]

    fused = reciprocal_rank_fusion([current, context], weights=[1.0, 0.5])

    assert [p.source_id for p in fused] == ["4", "2"]


def test_diversify_caps_passages_per_document_in_the_top_k_without_dropping_any() -> None:
    """#29: bir videonun ardışık parçaları ilk k'yı doldurmasın; fazlası sona iner, elenmez."""
    from dataclasses import replace

    from app.retrieval.hybrid import diversify

    ranked = [
        replace(passage("1"), document_id=7),
        replace(passage("2"), document_id=7),
        replace(passage("3"), document_id=7),
        replace(passage("4"), document_id=8),
        replace(passage("5"), document_id=7),
        replace(passage("6"), document_id=9),
    ]

    capped = diversify(ranked, 2, k=4)

    assert [p.source_id for p in capped] == ["1", "2", "4", "6", "3", "5"]
    assert diversify(ranked, None, k=4) == ranked
    # Aday azsa liste yine dolar: tek dokümanlı sonuçta sınır sırayı değiştirmez.
    single = [replace(passage(str(i)), document_id=7) for i in range(3)]
    assert diversify(single, 1, k=3) == single
