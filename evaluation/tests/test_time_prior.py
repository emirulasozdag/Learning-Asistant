from datetime import UTC, datetime

from harness.schemas import GoldItem, Playback, Review, SourceLocator
from harness.time_prior import (
    NO_PRIOR,
    Relation,
    Variant,
    coverage_gaps,
    recommend,
    relation,
    render_markdown,
    summarize,
    variants,
)

VIDEO_A, VIDEO_B, SLIDES = "a" * 64, "b" * 64, "c" * 64
REVIEW = Review(reviewer="instructor-1", reviewed_at=datetime(2026, 11, 2, tzinfo=UTC))


def item(id, evidence, video=VIDEO_A, time_s=300.0, playback=True):
    return GoldItem(
        id=id,
        split="calibration",
        kind="answerable",
        question=f"{id} bu adımı açıklar mısın?",
        reference_answer="...",
        evidence=evidence,
        origin="instructor",
        review=REVIEW,
        playback=Playback(document_sha256=video, time_s=time_s) if playback else None,
    )


def at(video, start, end):
    return SourceLocator(document_sha256=video, t_start=start, t_end=end)


def test_evidence_is_placed_relative_to_the_playback_position() -> None:
    assert relation(item("near", [at(VIDEO_A, 350, 380)]), 120) is Relation.NEAR
    assert relation(item("far", [at(VIDEO_A, 900, 930)]), 120) is Relation.FAR
    page = SourceLocator(document_sha256=SLIDES, page=4)
    assert relation(item("other", [page]), 120) is Relation.OTHER
    # Kanıtlardan biri pencere içindeyse yakın sayılır.
    assert relation(item("mixed", [page, at(VIDEO_A, 290, 310)]), 120) is Relation.NEAR
    # Aynı saniye, başka video: başka doküman.
    assert relation(item("other-video", [at(VIDEO_B, 300, 310)], video=VIDEO_A), 120) is (
        Relation.OTHER
    )


def test_summary_reports_recall_per_lecture_and_change_against_the_baseline() -> None:
    items = [
        item("a1", [at(VIDEO_A, 300, 320)]),
        item("a2", [SourceLocator(document_sha256=SLIDES, page=2)]),
        item("b1", [at(VIDEO_B, 100, 120)], video=VIDEO_B, time_s=110),
    ]
    baseline = {"a1": 8, "a2": 1, "b1": None}
    prior = {"a1": 1, "a2": 2, "b1": None}

    base = summarize(Variant(NO_PRIOR), items, baseline, None, 120)
    result = summarize(Variant("p", 120, 0.5), items, prior, baseline, 120)

    assert base.recall_at_5 == round(1 / 3, 4) and base.improved == base.worsened == 0
    assert result.recall_at_5 == round(2 / 3, 4)
    assert (result.improved, result.worsened, result.unchanged) == (1, 1, 1)
    assert result.by_lecture == {VIDEO_A: 1.0, VIDEO_B: 0.0}
    assert result.by_relation == {
        Relation.NEAR.value: 0.5,
        Relation.FAR.value: None,
        Relation.OTHER.value: 1.0,
    }


def test_recommendation_must_beat_the_baseline_without_hurting_document_evidence() -> None:
    items = [
        item("near", [at(VIDEO_A, 300, 320)]),
        item("doc", [SourceLocator(document_sha256=SLIDES, page=2)]),
    ]
    baseline = {"near": 9, "doc": 1}
    base = summarize(Variant(NO_PRIOR), items, baseline, None, 120)
    pushes_slides_down = summarize(
        Variant("güçlü", 120, 1.0), items, {"near": 1, "doc": 7}, baseline, 120
    )
    gentle = summarize(Variant("hafif", 120, 0.25), items, {"near": 2, "doc": 1}, baseline, 120)
    no_gain = summarize(Variant("etkisiz", 60, 0.25), items, baseline, baseline, 120)

    assert recommend([base, pushes_slides_down, gentle, no_gain]) == gentle
    assert recommend([base, pushes_slides_down]) is None
    assert recommend([base, no_gain]) is None


def test_production_setting_is_in_the_grid_and_marked() -> None:
    grid = variants(120.0, 0.5)

    assert grid[0].name == NO_PRIOR and not grid[0].uses_prior
    assert [v.name for v in grid if "(üretim)" in v.name] == [
        "pencere 120 sn, ağırlık 0.5 (üretim)"
    ]
    assert any("(üretim)" in v.name for v in variants(90.0, 0.7))


def test_missing_or_thin_playback_data_is_reported_not_filled() -> None:
    without = item("x", [at(VIDEO_A, 0, 5)], playback=False)
    assert "ölçülemedi" in coverage_gaps([], [without])[0]

    one_lecture = [item(f"q{i}", [at(VIDEO_A, 0, 5)]) for i in range(3)]
    gaps = coverage_gaps(one_lecture, [*one_lecture, without])

    assert any("1 kanıtlı soruda oynatma konumu yok" in g for g in gaps)
    assert any("tek bir derse" in g for g in gaps)
    assert any("küçük örnek" in g for g in gaps)


def test_markdown_lists_variants_lectures_and_gaps() -> None:
    items = [item("a1", [at(VIDEO_A, 300, 320)])]
    base = summarize(Variant(NO_PRIOR), items, {"a1": 3}, None, 120)
    report = {
        "comparison_id": "t1",
        "split": "heldout",
        "git_commit": "c" * 40,
        "git_dirty": False,
        "embedding_identity": "fake",
        "index_fingerprint": "f" * 64,
        "questions": {"with_playback": 1, "selected": 1},
        "production": {"video_window_s": 120.0, "video_weight": 0.5},
        "relation_window_s": 120.0,
        "lectures": [VIDEO_A],
        "variants": [base.__dict__],
        "recommended": None,
        "gaps": ["örnek boşluk"],
    }

    text = render_markdown(report)

    assert NO_PRIOR in text and f"`{VIDEO_A[:12]}`" in text
    assert "Held-out" in text and "- örnek boşluk" in text
