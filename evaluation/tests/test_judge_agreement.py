import pytest
from factories import NOW, labels, record, result

from harness.judge_agreement import (
    MIN_CALIBRATION_ANSWERS,
    _agreement,
    calibrate,
    cohen_kappa,
    compare,
    judge_trust,
)
from harness.labels import LabelSource
from harness.schemas import Split


def test_cohen_kappa_known_value():
    # Klasik örnek: po = 0.7, pe = 0.5 → κ = 0.4
    left = ["y"] * 20 + ["y"] * 5 + ["n"] * 10 + ["n"] * 15
    right = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohen_kappa(left, right) == pytest.approx(0.4)


def test_cohen_kappa_perfect_and_chance():
    assert cohen_kappa([0, 1, 2], [0, 1, 2]) == 1.0
    assert cohen_kappa(["a", "b", "a", "b"], ["a", "a", "b", "b"]) == pytest.approx(0.0)


def test_threshold_uses_unrounded_kappa():
    # 2x2 tablo 28/1/18/50 → κ ≈ 0,59996; yuvarlanmış 0,6 eşiği geçirmemeli.
    left = ["y"] * 28 + ["y"] * 1 + ["n"] * 18 + ["n"] * 50
    right = ["y"] * 28 + ["n"] * 1 + ["y"] * 18 + ["n"] * 50
    run = _run(1)
    a, b = labels(run, {}), labels(run, {}, rater="rater-b")
    agreement = _agreement(
        a, b, "score", [("q", None, x, y) for x, y in zip(left, right, strict=True)]
    )
    assert 0.5999 < agreement.kappa < 0.6
    assert not agreement.passes()


def test_cohen_kappa_undefined_cases():
    with pytest.raises(ValueError, match="payda"):
        cohen_kappa([], [])
    with pytest.raises(ValueError, match="uzunlukta"):
        cohen_kappa([1], [1, 2])
    with pytest.raises(ValueError, match="tanımsız"):
        cohen_kappa(["a", "a"], ["a", "a"])


def _run(n, split=Split.CALIBRATION):
    return record([result(f"q{i}") for i in range(n)], split=split)


def test_compare_lists_disagreements():
    run = _run(4)
    a = labels(run, {"q0": 2, "q1": 1, "q2": 0, "q3": 2})
    b = labels(
        run,
        {"q0": 2, "q1": 2, "q2": 0, "q3": 2},
        claims={"q3": ["supported", "unsupported"]},
        rater="rater-b",
    )
    scores, claims = compare(a, b)
    assert scores.n == 4 and scores.observed == 0.75
    assert [(d.item_id, d.left, d.right) for d in scores.disagreements] == [("q1", "1", "2")]
    assert claims.n == 8
    assert [(d.item_id, d.claim_index) for d in claims.disagreements] == [("q3", 1)]


def test_compare_skips_claims_with_changed_text():
    run = _run(1)
    a = labels(run, {"q0": 2})
    b = labels(run, {"q0": 2}, rater="rater-b", answer="Başka bir cevap cümlesi. İkinci bir cümle.")
    _, claims = compare(a, b)
    assert claims.n == 0 and "metni iki tarafta farklı" in claims.gap


def _calibration_inputs(n=MIN_CALIBRATION_ANSWERS, judge_flip=0):
    run = _run(n)
    scores = {f"q{i}": i % 3 for i in range(n)}
    claims = {
        f"q{i}": ["supported", "unsupported"][i % 2 :] + ["supported"] * (i % 2) for i in range(n)
    }
    humans = [
        labels(run, scores, claims, rater="rater-a"),
        labels(run, scores, claims, rater="rater-b"),
    ]
    judged = {k: (v + 1) % 3 if i < judge_flip else v for i, (k, v) in enumerate(scores.items())}
    judge = labels(run, judged, claims, rater="judge", source=LabelSource.JUDGE)
    return run, humans, judge


def test_calibration_passes_when_kappa_high():
    run, humans, judge = _calibration_inputs()
    calibration = calibrate(run, humans, judge, now=NOW)
    assert calibration.passed, calibration.reasons
    assert len(calibration.inter_rater) == 2 and len(calibration.judge_human) == 4
    assert judge_trust(calibration, judge, run) is None


def test_calibration_fails_on_low_judge_kappa():
    run, humans, judge = _calibration_inputs(judge_flip=MIN_CALIBRATION_ANSWERS)
    calibration = calibrate(run, humans, judge, now=NOW)
    assert not calibration.passed
    assert any("score uyumu" in reason for reason in calibration.reasons)
    assert judge_trust(calibration, judge, run) == "judge kalibrasyonu κ eşiğini geçmedi"


def test_calibration_needs_two_humans_and_enough_answers():
    run, humans, judge = _calibration_inputs(n=10)
    calibration = calibrate(run, humans[:1], judge, now=NOW)
    assert not calibration.passed
    assert any("İnsan değerlendirici 1/2" in r for r in calibration.reasons)
    assert any(f"10/{MIN_CALIBRATION_ANSWERS}" in r for r in calibration.reasons)


def test_calibration_refuses_heldout_runs():
    run, humans, judge = _calibration_inputs()
    heldout = run.model_copy(
        update={"config": run.config.model_copy(update={"split": Split.HELDOUT})}
    )
    with pytest.raises(ValueError, match="held-out"):
        calibrate(heldout, humans, judge)


def test_calibration_refuses_labels_of_other_run():
    run, humans, judge = _calibration_inputs()
    other = run.model_copy(update={"run_id": "run-x"})
    with pytest.raises(ValueError, match="başka bir koşu"):
        calibrate(other, humans, judge)


def test_trust_requires_same_judge_prompt_and_gold():
    run, humans, judge = _calibration_inputs()
    calibration = calibrate(run, humans, judge, now=NOW)
    assert judge_trust(None, judge, run) == "judge kalibre edilmedi"
    assert judge_trust(calibration, None, run) == "judge çalıştırılmadı"
    other_model = judge.model_copy(update={"judge_model": "google/gemini-3"})
    assert "aynı değil" in judge_trust(calibration, other_model, run)
    other_gold = run.model_copy(
        update={"config": run.config.model_copy(update={"gold_set_sha256": "x" * 64})}
    )
    assert "gold set" in judge_trust(calibration, judge, other_gold)
