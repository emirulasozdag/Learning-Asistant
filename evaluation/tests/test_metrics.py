import pytest

from harness.metrics.accuracy import fully_correct_rate
from harness.metrics.citation import evidence_coverage, precision_counts
from harness.metrics.hallucination import (
    answers_with_unsupported_claim_rate,
    unsupported_claim_rate,
)
from harness.metrics.retrieval import recall_at_k
from harness.metrics.scope import decline_rate, over_refusal_rate


def test_recall_basic():
    # soru 1: 2 gold'dan 1'i bulundu (0.5); soru 2: tamamı (1.0)
    assert recall_at_k([["a", "x"], ["b"]], [["a", "c"], ["b"]], k=5) == pytest.approx(0.75)


def test_recall_k_cutoff():
    retrieved = [["x", "y", "a"]]
    assert recall_at_k(retrieved, [["a"]], k=2) == 0.0
    assert recall_at_k(retrieved, [["a"]], k=3) == 1.0


def test_recall_skips_items_without_evidence():
    assert recall_at_k([["a"], ["zzz"]], [["a"], []]) == 1.0


def test_recall_custom_match():
    assert recall_at_k([[10]], [[5]], match=lambda g, r: r > g) == 1.0


def test_recall_length_mismatch():
    with pytest.raises(ValueError, match="uzunlukta"):
        recall_at_k([["a"]], [["a"], ["b"]])


def test_recall_no_evidence_at_all():
    with pytest.raises(ValueError, match="Gold kanıtı"):
        recall_at_k([["a"]], [[]])


def test_recall_invalid_k():
    with pytest.raises(ValueError):
        recall_at_k([["a"]], [["a"]], k=0)


def test_decline_and_over_refusal_rates():
    assert decline_rate([True, True, True, False]) == 0.75
    assert over_refusal_rate([False, False, False, True]) == 0.25


@pytest.mark.parametrize("fn", [decline_rate, over_refusal_rate])
def test_rates_empty_denominator(fn):
    with pytest.raises(ValueError, match="payda"):
        fn([])


# --- Doğruluk, hallucination, alıntı kapsamı ---------------------------------------------------


def test_fully_correct_rate():
    assert fully_correct_rate([2, 2, 1, 0]) == 0.5
    with pytest.raises(ValueError, match="payda"):
        fully_correct_rate([])
    with pytest.raises(ValueError, match="0, 1 ya da 2"):
        fully_correct_rate([3])


def test_hallucination_rates():
    labels = [["supported", "unsupported"], ["supported"], []]
    # 3 cevaptan 1'inde desteklenmeyen iddia; 3 iddiadan 1'i desteklenmiyor.
    assert answers_with_unsupported_claim_rate(labels) == pytest.approx(1 / 3)
    assert unsupported_claim_rate(labels) == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="payda"):
        unsupported_claim_rate([[]])
    with pytest.raises(ValueError, match="etiket"):
        answers_with_unsupported_claim_rate([["maybe"]])


def test_citation_coverage_and_precision():
    cited = [["a", "x"], ["z"], ["b"]]
    gold = [["a", "c"], ["b"], []]
    # soru 1: 2 kanıttan 1'i alıntılandı; soru 2: hiçbiri; 3. soru kanıtsız → hesaba katılmaz.
    assert evidence_coverage(cited, gold) == pytest.approx(0.25)
    assert precision_counts(cited, gold) == (1, 3)
    with pytest.raises(ValueError, match="Gold kanıtı"):
        evidence_coverage([["a"]], [[]])
