from harness.retrieval_sweep import (
    GateCell,
    ItemSignals,
    first_hit_rank,
    gate_grid,
    gate_passes,
    recommend,
)
from harness.schemas import SourceLocator

SHA = "a" * 64


def signals(kind: str, similarity: float | None, coverage: float | None) -> ItemSignals:
    return ItemSignals(
        id=f"{kind}-{similarity}-{coverage}",
        kind=kind,
        best_similarity=similarity,
        keyword_coverage=coverage,
    )


def test_gate_passes_on_meaning_or_keyword_coverage() -> None:
    assert gate_passes(signals("answerable", 0.80, None), 0.78, 0.5)
    assert gate_passes(signals("answerable", 0.70, 0.6), 0.78, 0.5)
    assert not gate_passes(signals("answerable", 0.70, 0.4), 0.78, 0.5)
    assert not gate_passes(signals("answerable", None, None), 0.78, 0.5)


def test_recommend_maximizes_decline_within_over_refusal_target() -> None:
    cells = [
        GateCell(0.76, 0.5, over_refusal=0.0, out_of_scope_decline=0.5),
        GateCell(0.78, 0.5, over_refusal=0.05, out_of_scope_decline=0.8),
        GateCell(0.80, 0.5, over_refusal=0.2, out_of_scope_decline=1.0),  # hedef dışı
    ]

    assert recommend(cells) == cells[1]
    assert recommend([cells[2]]) is None


def test_gate_grid_counts_refusals_per_kind() -> None:
    items = [signals("answerable", 0.85, None), signals("out_of_scope", 0.74, 0.2)]

    cell = next(
        c for c in gate_grid(items) if (c.min_similarity, c.min_keyword_coverage) == (0.78, 0.5)
    )

    assert (cell.over_refusal, cell.out_of_scope_decline) == (0.0, 1.0)


def test_first_hit_rank_matches_gold_locator() -> None:
    hits = [SourceLocator(document_sha256=SHA, page=p) for p in (3, 7, 9)]

    assert first_hit_rank(hits, [SourceLocator(document_sha256=SHA, page=7)]) == 2
    assert first_hit_rank(hits, [SourceLocator(document_sha256=SHA, page=1)]) is None


def test_unresolved_candidates_keep_their_rank() -> None:
    gold = [SourceLocator(document_sha256=SHA, page=7)]

    assert first_hit_rank([None, None, SourceLocator(document_sha256=SHA, page=7)], gold) == 3
