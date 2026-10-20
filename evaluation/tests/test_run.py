from datetime import UTC, datetime

import pytest

from harness.conditions import Condition
from harness.run import (
    Answer,
    _percentile,
    _sanitized_url,
    compute_metrics,
    evaluate,
    run_id_for,
    select_items,
    write_outputs,
)
from harness.schemas import (
    CorpusSnapshot,
    GoldItem,
    ItemKind,
    ItemResult,
    RunConfig,
    RunRecord,
    SourceLocator,
    Split,
)

SHA = "a" * 64
REVIEW = {"reviewer": "instructor-1", "reviewed_at": "2026-10-01T10:00:00Z"}


def gold(id, split="heldout", kind="answerable", reviewed=True, evidence=None):
    data = {
        "id": id,
        "split": split,
        "kind": kind,
        "question": f"Soru {id}?",
        "origin": "instructor",
        "review": REVIEW if reviewed else None,
    }
    if evidence:
        data["evidence"] = evidence
    return GoldItem(**data)


def locator(page=1):
    return SourceLocator(document_sha256=SHA, page=page)


def answer(**kw):
    data = {
        "outcome": "answered",
        "declined": False,
        "mode": "llm",
        "model": "m",
        "text": "cevap",
        "cited_source_ids": [],
        "retrieved_source_ids": [],
        "best_similarity": 0.5,
    }
    return Answer(**{**data, **kw})


def result(id="q", kind=ItemKind.ANSWERABLE, **kw):
    data = {
        "id": id,
        "split": Split.HELDOUT,
        "kind": kind,
        "outcome": "answered",
        "declined": False,
        "mode": "llm",
        "model": "m",
        "answer": "a",
    }
    return ItemResult(**{**data, **kw})


# --- select_items ------------------------------------------------------------------------------


def test_select_items_keeps_splits_apart():
    items = [gold("c1", "calibration"), gold("h1", "heldout")]
    selected, gaps = select_items(items, Split.HELDOUT, include_unreviewed=False)
    assert [i.id for i in selected] == ["h1"]
    assert gaps == []
    selected, _ = select_items(items, Split.CALIBRATION, include_unreviewed=False)
    assert [i.id for i in selected] == ["c1"]


def test_select_items_none_split_takes_all():
    items = [gold("c1", "calibration"), gold("h1", "heldout")]
    assert len(select_items(items, None, include_unreviewed=False)[0]) == 2


def test_select_items_skips_unreviewed_with_gap():
    items = [gold("ok"), gold("u1", reviewed=False), gold("u2", reviewed=False)]
    selected, gaps = select_items(items, None, include_unreviewed=False)
    assert [i.id for i in selected] == ["ok"]
    assert len(gaps) == 1 and "2 soru" in gaps[0] and "u1" in gaps[0]


def test_select_items_unreviewed_gap_truncates_ids():
    items = [gold(f"u{n}", reviewed=False) for n in range(12)]
    _, gaps = select_items(items, None, include_unreviewed=False)
    assert "u9" in gaps[0] and "u10" not in gaps[0] and "…" in gaps[0]


def test_select_items_include_unreviewed():
    items = [gold("ok"), gold("u", reviewed=False)]
    selected, gaps = select_items(items, None, include_unreviewed=True)
    assert len(selected) == 2 and gaps == []


# --- evaluate ----------------------------------------------------------------------------------


def test_evaluate_records_error_and_continues():
    def ask(question):
        if "bad" in question:
            raise RuntimeError("boom")
        return answer()

    results = evaluate([gold("bad"), gold("good")], ask, lambda sid: None)
    assert results[0].error == "RuntimeError: boom"
    assert results[0].outcome is None and results[0].declined is None
    assert results[1].error is None and results[1].outcome == "answered"


def test_evaluate_locates_ids_and_drops_none():
    known = {"s1": locator(1), "s2": locator(2)}

    def ask(question):
        return answer(cited_source_ids=["s1", "gone"], retrieved_source_ids=["s2", "gone", "s1"])

    [res] = evaluate([gold("q")], ask, known.get)
    assert res.cited == [locator(1)]
    assert res.retrieved == [locator(2), locator(1)]


def test_evaluate_latency_uses_injected_clock():
    ticks = iter([1.0, 1.25])
    [res] = evaluate([gold("q")], lambda q: answer(), lambda s: None, clock=lambda: next(ticks))
    assert res.latency_ms == 250.0


# --- compute_metrics ---------------------------------------------------------------------------


def test_metrics_exclude_errored_items():
    items = [gold("a"), gold("b"), gold("o", kind="out_of_scope")]
    results = [
        result("a"),
        result("b", outcome=None, declined=None, error="X: y"),
        result("o", ItemKind.OUT_OF_SCOPE, declined=True),
    ]
    metrics, gaps = compute_metrics(items, results)
    assert metrics["answerable_over_refusal_rate"].denominator == 1
    assert metrics["out_of_scope_decline_rate"].value == 1.0
    assert metrics["provider_failure_rate"].denominator == 2
    assert any("1 soru hata verdi" in g for g in gaps)


def test_metrics_judge_values_are_none_with_gap():
    metrics, _ = compute_metrics([gold("a")], [result("a")])
    for name in ("answer_fully_correct_rate", "answers_with_unsupported_claim_rate"):
        assert metrics[name].value is None and metrics[name].gap


def test_metrics_reviewed_minimum_gap():
    _, gaps = compute_metrics([gold("a")], [result("a")])
    assert any("1/30" in g for g in gaps)
    assert any("Kapsam dışı soru 0/30" in g for g in gaps)


def test_metrics_no_minimum_gap_when_enough_items():
    items = [gold(f"a{n}") for n in range(30)] + [
        gold(f"o{n}", kind="out_of_scope") for n in range(30)
    ]
    _, gaps = compute_metrics(items, [])
    assert not any("/30" in g for g in gaps)


def test_metrics_recall_citation_and_declines():
    items = [gold("a", evidence=[locator(1)]), gold("b", evidence=[locator(2)]), gold("c")]
    results = [
        result("a", retrieved=[locator(1)], cited=[locator(1)], latency_ms=10.0),
        result("b", retrieved=[locator(9)], latency_ms=30.0),
        result("c", declined=True, outcome="declined"),
    ]
    metrics, _ = compute_metrics(items, results)
    recall = metrics["retrieval_recall_at_5"]
    assert (recall.value, recall.denominator) == (0.5, 2)
    assert metrics["answerable_over_refusal_rate"].numerator == 1
    citation = metrics["citation_presence_rate"]
    assert (citation.numerator, citation.denominator) == (1, 2)
    assert metrics["latency_p50_ms"].value == 20.0


def test_metrics_empty_denominators_give_gap_not_error():
    metrics, _ = compute_metrics([], [])
    for name in ("retrieval_recall_at_5", "out_of_scope_decline_rate", "latency_p95_ms"):
        assert metrics[name].value is None and metrics[name].gap


def test_provider_failure_rate():
    results = [result("a", outcome="provider_failure"), result("b")]
    metrics, _ = compute_metrics([gold("a"), gold("b")], results)
    assert metrics["provider_failure_rate"].value == 0.5


# --- _percentile / run_id_for ------------------------------------------------------------------


def test_percentile_small_samples():
    assert _percentile([5.0], 0.95) == 5.0
    assert _percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    assert _percentile([1.0, 2.0, 3.0], 0.0) == 1.0
    assert _percentile([1.0, 2.0], 0.95) == 2.0


def test_percentile_nearest_rank():
    # En yakın sıra yöntemi: 20 değerde p95 = 19. değer (indeks 18)
    values = [float(n) for n in range(1, 21)]
    assert _percentile(values, 0.95) == 19.0


def test_run_id_for():
    started = datetime(2026, 10, 20, 9, 8, 7, tzinfo=UTC)
    first = run_id_for(started, Condition.FULL, Split.HELDOUT, "0123456789abcdef")
    second = run_id_for(started, Condition.FULL, Split.HELDOUT, "0123456789abcdef")

    assert first.startswith("20261020T090807Z_full_heldout_01234567_")
    assert first != second  # aynı saniyedeki iki koşu çakışmaz
    assert run_id_for(started, Condition.FULL, None, None).startswith(
        "20261020T090807Z_full_all_nogit_"
    )


def test_sanitized_url_keeps_endpoint_but_drops_secrets():
    assert _sanitized_url("http://user:pw@localhost:9000/custom/v1?key=x") == (
        "http://localhost:9000/custom/v1"
    )


def test_write_outputs_never_overwrites(tmp_path):
    config = RunConfig(
        condition="full", split=None, git_commit=None, git_dirty=None,
        gold_set_sha256=SHA, manifest_sha256=SHA, llm_provider="p", llm_model=None,
        llm_base_url="https://x/v1", llm_enabled=False, prompt_sha256=SHA,
        embedding_provider="e", embedding_model="m", retrieval={"k": 5},
    )  # fmt: skip
    record = RunRecord(
        run_id="run1",
        started_at=datetime(2026, 10, 20, tzinfo=UTC),
        config=config,
        corpus=CorpusSnapshot(course_code="BLM2512", documents=[]),
    )
    write_outputs(record, tmp_path)

    with pytest.raises(FileExistsError):
        write_outputs(record, tmp_path)
