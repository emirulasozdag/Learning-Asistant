"""Görsel koşul ve görsel soru etiketleri (#30): transcript-only ile görsel bağlam ayrılır,
beklenen davranış (cevap / netleştirme / ret) ölçülür, kare alıntıları kaybolmaz."""

import pytest
from pydantic import ValidationError

from harness import conditions
from harness.conditions import Condition
from harness.run import (
    Answer,
    compute_metrics,
    compute_visual_metrics,
    condition_gaps,
    evaluate,
    parse_conditions,
)
from harness.schemas import GoldItem, ItemKind, ItemResult, Playback, SourceLocator, Split

SHA = "a" * 64
VIDEO = "b" * 64
REVIEW = {"reviewer": "instructor-1", "reviewed_at": "2026-10-01T10:00:00Z"}
PLAYBACK = Playback(document_sha256=VIDEO, time_s=200.0)


def gold(id="q", visual=None, playback=PLAYBACK, reviewed=True, **kw):
    data = {
        "id": id,
        "split": "heldout",
        "kind": "answerable",
        "question": f"Soru {id}?",
        "reference_answer": "ref",
        "evidence": [SourceLocator(document_sha256=VIDEO, t_start=190.0, t_end=410.0)],
        "origin": "team_draft",
        "review": REVIEW if reviewed else None,
        "playback": playback,
        "visual": visual,
    }
    return GoldItem(**{**data, **kw})


def label(expected="answer", support="visual", frame_kind="diagram", trap=None):
    return {"frame_kind": frame_kind, "expected": expected, "support": support, "trap": trap}


def result(id="q", outcome="answered", **kw):
    data = {
        "id": id,
        "split": Split.HELDOUT,
        "kind": ItemKind.ANSWERABLE,
        "outcome": outcome,
        "declined": outcome != "answered",
        "mode": "llm",
        "model": "m",
        "answer": "a" if outcome == "answered" else None,
    }
    return ItemResult(**{**data, **kw})


# --- Şema ---


def test_visual_label_requires_a_playback_position() -> None:
    with pytest.raises(ValidationError, match="playback"):
        gold(visual=label(), playback=None)


def test_out_of_scope_item_cannot_have_a_visual_label() -> None:
    with pytest.raises(ValidationError, match="görsel etiket"):
        GoldItem(
            id="o",
            split="heldout",
            kind="out_of_scope",
            question="Hava nasıl?",
            origin="team_draft",
            playback=PLAYBACK,
            visual=label(expected="decline"),
        )


def test_unknown_visual_label_values_are_rejected() -> None:
    with pytest.raises(ValidationError):
        gold(visual=label(frame_kind="photo"))
    with pytest.raises(ValidationError):
        gold(visual={**label(), "guess": True})


# --- Koşul ---


def test_visual_differs_from_full_video_time_only_by_frames() -> None:
    transcript = conditions.SETTINGS[Condition.FULL_VIDEO_TIME]
    visual = conditions.SETTINGS[Condition.VISUAL]

    assert transcript["frames"] is False and visual["frames"] is True
    assert {k: v for k, v in visual.items() if k != "frames"} == {
        k: v for k, v in transcript.items() if k != "frames"
    }
    assert all(
        settings["frames"] is False
        for c, settings in conditions.SETTINGS.items()
        if c is not Condition.VISUAL
    )
    assert Condition.VISUAL in parse_conditions(["all"])


def test_visual_condition_reports_a_course_without_frames() -> None:
    gaps = condition_gaps(Condition.VISUAL, [gold()], frame_count=0)
    assert any("kare yok" in gap for gap in gaps)
    assert not any(
        "kare yok" in g for g in condition_gaps(Condition.VISUAL, [gold()], frame_count=3)
    )
    assert condition_gaps(Condition.FULL_VIDEO_TIME, [gold()], frame_count=0) == []
    assert condition_gaps(Condition.FULL, [gold()], frame_count=0) == []


# --- Kayıt: kare alıntısı ve köken ---


def test_frame_citations_and_check_provenance_are_kept() -> None:
    locate = {
        "11": SourceLocator(document_sha256=SHA, page=2),
        "frame:7": SourceLocator(document_sha256=VIDEO, t_start=190.0, t_end=410.0),
    }.get
    answer = Answer(
        outcome="answered",
        declined=False,
        mode="llm",
        model="gen",
        text="cevap",
        cited_source_ids=["11", "frame:7"],
        retrieved_source_ids=["11"],
        best_similarity=0.6,
        retrieved_texts=["metin"],
        claim_check="checked",
        judge_model="judge",
        visual_gap="source_conflict",
    )

    [item] = evaluate([gold()], lambda q: answer, locate)

    assert item.cited_frames == 1 and len(item.cited) == 2
    assert item.cited[1].t_start == 190.0
    assert (item.claim_check, item.judge_model, item.visual_gap) == (
        "checked",
        "judge",
        "source_conflict",
    )


# --- Metrikler ---


def test_expected_behavior_trap_and_contradiction_metrics() -> None:
    items = [
        gold("a", visual=label("answer")),
        gold("c", visual=label("clarify", frame_kind="ambiguous")),
        gold("t", visual=label("decline", trap="temporal")),
        gold("x", visual=label("answer", support="contradiction")),
        gold("plain"),  # etiketsiz: görsel metriklere girmez
    ]
    results = [
        result("a", cited_frames=1),
        result("c", outcome="needs_clarification", visual_gap="scene_ambiguous"),
        result("t", outcome="answered"),  # tuzağa düştü
        result("x", visual_gap="source_conflict"),
        result("plain"),
    ]

    metrics, gaps = compute_visual_metrics(items, results)

    assert metrics["visual_expected_behavior_rate"].numerator == 3
    assert metrics["visual_expected_behavior_rate"].denominator == 4
    assert metrics["visual_trap_safe_rate"].value == 0.0
    assert metrics["visual_contradiction_safe_rate"].value == 1.0
    assert metrics["clarification_rate"].numerator == 1
    assert metrics["answers_citing_frames_rate"].numerator == 1
    assert metrics["answers_citing_frames_rate"].denominator == 3
    assert metrics["visual_claim_support_rate"].value is None
    assert gaps == []


def test_decline_expectation_accepts_a_clarification_or_an_insufficient_evidence_decline() -> None:
    items = [gold("d1", visual=label("decline")), gold("d2", visual=label("decline"))]
    results = [
        result("d1", outcome="insufficient_evidence", visual_gap="frame_insufficient"),
        result("d2", outcome="needs_clarification"),
    ]

    metrics, _ = compute_visual_metrics(items, results)

    assert metrics["visual_expected_behavior_rate"].value == 1.0
    assert metrics["frame_insufficient_rate"].value == 0.5


def test_unreviewed_visual_items_are_flagged() -> None:
    _, gaps = compute_visual_metrics([gold(visual=label(), reviewed=False)], [result()])
    assert any("incelemesinden geçmedi" in gap for gap in gaps)


def test_visual_metrics_appear_only_in_playback_conditions() -> None:
    items, results = [gold(visual=label())], [result()]

    transcript, _ = compute_metrics(items, results, Condition.FULL_VIDEO_TIME)
    visual, _ = compute_metrics(items, results, Condition.VISUAL)
    full, _ = compute_metrics(items, results, Condition.FULL)

    assert "visual_expected_behavior_rate" in transcript
    assert "visual_expected_behavior_rate" in visual
    assert "visual_expected_behavior_rate" not in full


def test_no_labelled_items_gives_a_gap() -> None:
    metrics, gaps = compute_visual_metrics([gold()], [result()])
    assert metrics == {} and "Görsel etiketli soru yok" in gaps[0]


# --- Görsel set kapsaması ---


def test_visual_coverage_lists_missing_case_types_and_review_count() -> None:
    from harness.schemas import GoldSet
    from harness.validate import visual_coverage_gaps

    gold_set = GoldSet(
        course_code="18.06",
        manifest="manifest.json",
        items=[
            gold("a", visual=label(support="mixed"), reviewed=False),
            gold("b", visual=label("decline", frame_kind="ambiguous", trap="temporal")),
        ],
    )

    gaps = visual_coverage_gaps(gold_set)

    assert "formül" in gaps[0] and "kod" in gaps[0] and "görüntü–metin çelişkisi" in gaps[0]
    assert "diyagram" not in gaps[0] and "zamansal tuzak" not in gaps[0]
    assert gaps[1] == "Eğitmen/TA incelemeli görsel soru 1/30"


def test_visual_coverage_is_silent_without_visual_items() -> None:
    from harness.schemas import GoldSet
    from harness.validate import visual_coverage_gaps

    assert visual_coverage_gaps(GoldSet(course_code="x1", manifest="m", items=[gold()])) == []
