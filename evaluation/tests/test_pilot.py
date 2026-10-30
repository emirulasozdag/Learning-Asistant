"""İnsan örneklemi metrikleri (#18): QWK, pratik kabulü, SUS, memnuniyet ve eksik etiketler."""

import json

import pytest
from pydantic import ValidationError

from harness.metrics.grading_agreement import quadratic_weighted_kappa
from harness.metrics.practice_quality import acceptable_rate
from harness.metrics.usability import satisfaction_mean, sus_respondent_score, sus_score
from harness.pilot import (
    PLANNED_PRACTICE_ITEMS,
    GradingSet,
    PracticeReview,
    SurveyResponse,
    SurveySet,
    build_report,
    main,
)

NOW = "2026-11-20T10:00:00Z"

# --- Metrikler ---


def test_qwk_perfect_and_partial_agreement():
    assert quadratic_weighted_kappa([0, 1, 2, 2], [0, 1, 2, 2]) == pytest.approx(1.0)
    # Elle hesaplanan: tek bir 1 puanlık fark, 0–3 aralığında.
    assert quadratic_weighted_kappa([0, 1, 2, 3], [0, 2, 2, 3], 0, 3) == pytest.approx(0.9)


def test_qwk_penalises_large_disagreement_more():
    near = quadratic_weighted_kappa([0, 1, 2, 3, 4], [1, 1, 2, 3, 4], 0, 4)
    far = quadratic_weighted_kappa([0, 1, 2, 3, 4], [4, 1, 2, 3, 4], 0, 4)
    assert near > far


@pytest.mark.parametrize(
    ("a", "b", "kw"),
    [
        ([], [], {}),
        ([1, 2], [1], {}),
        ([1, 1], [1, 1], {}),
        ([0, 5], [0, 1], {"min_score": 0, "max_score": 4}),
    ],
    ids=["empty", "length", "constant", "range"],
)
def test_qwk_rejects_undefined_inputs(a, b, kw):
    with pytest.raises(ValueError):
        quadratic_weighted_kappa(a, b, **kw)


def test_acceptable_rate():
    assert acceptable_rate([True, True, False, True]) == 0.75
    with pytest.raises(ValueError):
        acceptable_rate([])


def test_sus_scoring_follows_item_polarity():
    assert sus_respondent_score([5, 1] * 5) == 100.0
    assert sus_respondent_score([1, 5] * 5) == 0.0
    assert sus_respondent_score([3] * 10) == 50.0
    assert sus_score([[5, 1] * 5, [3] * 10]) == 75.0
    with pytest.raises(ValueError):
        sus_respondent_score([3] * 9)
    with pytest.raises(ValueError):
        sus_respondent_score([0] + [3] * 9)


def test_satisfaction_mean():
    assert satisfaction_mean([4, 5, 3]) == 4.0
    with pytest.raises(ValueError):
        satisfaction_mean([6])


# --- Şemalar ---


def test_rejected_practice_item_needs_a_reason():
    with pytest.raises(ValidationError):
        PracticeReview(item_ref="12", acceptable=False)


def test_grading_scores_must_fit_the_rubric_range():
    with pytest.raises(ValidationError):
        GradingSet(
            course_code="BLM2512", rater="ta-1", rated_at=NOW, min_score=0, max_score=4,
            blind=True, items=[{"attempt_ref": "7", "assistant_score": 5, "instructor_score": 4}],
        )  # fmt: skip


def test_survey_rejects_identifiers_and_duplicates():
    with pytest.raises(ValidationError):
        SurveyResponse(participant="20231234", consent_version="2026-10-20")
    with pytest.raises(ValidationError):
        SurveySet(
            course_code="BLM2512",
            instrument_version="v1",
            responses=[
                {"participant": "p01", "consent_version": "v"},
                {"participant": "p01", "consent_version": "v"},
            ],
        )


# --- Rapor ---


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_report_without_labels_records_gaps_not_values(tmp_path):
    report = build_report(tmp_path)

    assert report.metrics["practice_acceptable_rate"].value is None
    assert report.metrics["grading_qwk"].value is None
    assert report.metrics["sus_mean"].value is None
    assert len(report.gaps) == 3


def test_report_computes_metrics_and_workload(tmp_path):
    write(
        tmp_path / "practice_review.ta-1.json",
        {
            "course_code": "BLM2512",
            "reviewer": "ta-1",
            "reviewed_at": NOW,
            "minutes_spent": 30,
            "items": [
                {"item_ref": "1", "acceptable": True},
                {"item_ref": "2", "acceptable": False, "issues": ["ambiguous"]},
            ],
        },
    )
    write(
        tmp_path / "grading.instructor-1.json",
        {
            "course_code": "BLM2512",
            "rater": "instructor-1",
            "rated_at": NOW,
            "min_score": 0,
            "max_score": 3,
            "blind": False,
            "items": [
                {"attempt_ref": str(n), "assistant_score": a, "instructor_score": b}
                for n, (a, b) in enumerate([(0, 0), (1, 2), (2, 2), (3, 3)])
            ],
        },
    )
    write(
        tmp_path / "survey.json",
        {
            "course_code": "BLM2512",
            "instrument_version": "v1",
            "responses": [
                {
                    "participant": "p01",
                    "consent_version": "v",
                    "sus": [5, 1] * 5,
                    "satisfaction": 5,
                },
                {"participant": "p02", "consent_version": "v", "sus": None, "satisfaction": 3},
            ],
        },
    )
    report = build_report(tmp_path)

    practice = report.metrics["practice_acceptable_rate.ta-1"]
    assert (practice.value, practice.denominator) == (0.5, 2)
    assert f"2/{PLANNED_PRACTICE_ITEMS}" in (practice.gap or "")
    qwk = report.metrics["grading_qwk.instructor-1"]
    assert qwk.value == pytest.approx(0.9)
    assert "kör değil" in (qwk.gap or "")
    assert report.metrics["sus_mean"].value == 100.0
    assert report.metrics["sus_mean"].denominator == 1
    assert report.metrics["satisfaction_mean"].value == 4.0
    assert report.gaps == [
        "instructor-1: harcanan süre (minutes_spent) yazılmamış; iş yükü ölçülemedi"
    ]
    assert report.workload == ["ta-1: 2 birim, 30 dk (birim başına 15.0 dk)"]


def test_cli_writes_report(tmp_path, capsys):
    out = tmp_path / "out"
    assert main(["--labels", str(tmp_path), "--out", str(out)]) == 0
    assert len(list(out.glob("pilot_*.json"))) == 1
    assert "İnsan örneklemi metrikleri" in capsys.readouterr().out
