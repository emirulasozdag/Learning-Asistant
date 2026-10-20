import pytest

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
