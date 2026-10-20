import pytest
from factories import NOW, labels, record, result

from harness.judge_agreement import calibrate
from harness.labels import LabelSource, draw_sample
from harness.schemas import ItemKind, MetricValue, Split
from harness.trust import headline_metrics, label_metrics, render_trust_report


def _run():
    return record(
        [
            result("q1"),
            result("q2"),
            result("q3", declined=True),
            result("o1", kind=ItemKind.OUT_OF_SCOPE, declined=True),
            result("e1", error="X: y"),
        ]
    )


def test_label_metrics_denominators():
    run = _run()
    rater = labels(run, {"q1": 2, "q2": 1}, claims={"q2": ["supported", "unsupported"]})
    metrics = label_metrics(run, rater)

    accuracy = metrics["answer_fully_correct_rate"]
    # Payda: hatasız cevaplanabilir sorular (q1, q2, reddedilen q3 = 0 puan).
    assert (accuracy.numerator, accuracy.denominator) == (1, 3)
    per_answer = metrics["answers_with_unsupported_claim_rate"]
    assert (per_answer.numerator, per_answer.denominator, per_answer.value) == (1, 2, 0.5)
    per_claim = metrics["unsupported_claim_rate"]
    assert (per_claim.numerator, per_claim.denominator) == (1, 4)


def test_label_metrics_restricted_to_sample():
    run = _run()
    rater = labels(run, {"q1": 2})
    metrics = label_metrics(run, rater, item_ids={"q1", "q3"})
    assert metrics["answer_fully_correct_rate"].denominator == 2
    assert metrics["answer_fully_correct_rate"].value == 0.5


def test_unlabeled_answers_give_gap_not_value():
    run = _run()
    metrics = label_metrics(run, labels(run, {"q1": 2}))
    for metric in metrics.values():
        assert metric.value is None and metric.gap


def test_uncalibrated_judge_is_not_authoritative():
    run = _run()
    run.metrics["answer_fully_correct_rate"] = MetricValue(value=None, denominator=3)
    judge = labels(run, {"q1": 2, "q2": 2}, rater="judge", source=LabelSource.JUDGE)
    metrics = headline_metrics(run, judge, "judge kalibre edilmedi")
    assert metrics["answer_fully_correct_rate"].value is None
    assert "otoriter değil" in metrics["answer_fully_correct_rate"].gap
    trusted = headline_metrics(run, judge, None)
    assert trusted["answer_fully_correct_rate"].value == round(2 / 3, 4)


def test_report_without_labels_lists_gaps():
    run = _run()
    run.gaps.append("Maliyet (token/ücret) kaydedilmiyor")
    report = render_trust_report(run, None, [], None, None)
    assert "İnsan etiketi yok" in report
    assert "Judge sonuçları otoriter değil: judge çalıştırılmadı" in report
    assert "Maliyet" in report
    # Rapor metin taşımaz: cevap ve pasaj metni yok.
    assert "İkili arama" not in report


def test_report_with_humans_judge_and_calibration():
    n = 40
    run = record([result(f"q{i}") for i in range(n)], split=Split.CALIBRATION)
    scores = {f"q{i}": i % 3 for i in range(n)}
    claims = {
        f"q{i}": ["supported", "unsupported"] if i % 2 else ["supported"] * 2 for i in range(n)
    }
    a = labels(run, scores, claims, rater="rater-a")
    b_scores = dict(scores, q0=1)
    b = labels(run, b_scores, claims, rater="rater-b")
    judge = labels(run, scores, claims, rater="judge", source=LabelSource.JUDGE)
    calibration = calibrate(run, [a, b], judge, now=NOW)
    sample = draw_sample(run, size=n, seed=1, now=NOW)

    report = render_trust_report(run, sample, [a, b], judge, calibration)

    assert "otoriter (kalibre)" in report
    assert "rater-a – rater-b" in report and "judge – rater-a" in report
    assert "## Anlaşmazlıklar" in report and "`q0`" in report
    assert "Judge sonuçları" in report and "ön sonuçları" not in report
    assert "Kalibrasyon (`run-1`" in report


def test_report_marks_heldout_agreement_as_verification_only():
    run = record([result("q1"), result("q2")], split=Split.HELDOUT)
    a = labels(run, {"q1": 2, "q2": 1}, rater="rater-a")
    judge = labels(run, {"q1": 2, "q2": 1}, rater="judge", source=LabelSource.JUDGE)
    report = render_trust_report(run, None, [a], judge, None)
    assert "yalnızca doğrulamadır" in report
    assert "ön sonuçları (otoriter değil)" in report
    assert "İnsan değerlendirici 1/2" in report


def test_stale_claim_labels_are_not_counted():
    run = _run()
    rater = labels(run, {"q1": 2, "q2": 2})
    # Aynı sayıda iddia ama metin değişmiş (eski bölme kuralı ya da eski cevap).
    stale = rater.items[0].claims[0].model_copy(update={"claim_sha256": "0" * 64})
    rater.items[0].claims[0] = stale
    metrics = label_metrics(run, rater)
    assert metrics["answers_with_unsupported_claim_rate"].value is None
    assert "eksik etiketli" in metrics["answers_with_unsupported_claim_rate"].gap


def test_report_rejects_labels_or_sample_of_other_run():
    run = _run()
    other = record([result("q1")], run_id="run-x")
    with pytest.raises(ValueError, match="başka bir koşu"):
        render_trust_report(run, None, [labels(other, {"q1": 2})], None, None)
    with pytest.raises(ValueError, match="Örneklem"):
        render_trust_report(run, draw_sample(other, 1, seed=1), [], None, None)
