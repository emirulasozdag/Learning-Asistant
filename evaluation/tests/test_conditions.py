"""Dört koşul (#18): temel çizgi hatları, koşula duyarlı metrikler, karşılaştırma raporu."""

from datetime import UTC, datetime

import pytest

from app.llm.base import LLMError, LLMRefusal
from harness import conditions
from harness.conditions import Condition, Passage, basic_rag, closed_book
from harness.report import render_comparison
from harness.run import (
    compute_metrics,
    condition_gaps,
    parse_conditions,
    write_comparison,
)
from harness.schemas import (
    CorpusSnapshot,
    GoldItem,
    ItemKind,
    ItemResult,
    MetricValue,
    Playback,
    RunConfig,
    RunRecord,
    SourceLocator,
    Split,
)

SHA = "a" * 64
REVIEW = {"reviewer": "instructor-1", "reviewed_at": "2026-10-01T10:00:00Z"}


class FakeText:
    model = "gen-model"

    def __init__(self, text="", error=None):
        self.text, self.error = text, error
        self.calls = []

    def stream_text(self, system, messages):
        self.calls.append((system, messages))
        if self.error:
            raise self.error
        yield self.text


def gold(id="q", playback=None, evidence=True):
    return GoldItem(
        id=id,
        split="heldout",
        kind="answerable",
        question=f"Soru {id}?",
        reference_answer="ref",
        evidence=[SourceLocator(document_sha256=SHA, page=1)] if evidence else [],
        origin="instructor",
        review=REVIEW,
        playback=playback,
    )


def result(id="q", **kw):
    data = {
        "id": id,
        "split": Split.HELDOUT,
        "kind": ItemKind.ANSWERABLE,
        "outcome": "answered",
        "declined": False,
        "mode": "llm",
        "model": "gen-model",
        "answer": "a",
    }
    return ItemResult(**{**data, **kw})


def config(condition, batch="b1", index="i" * 64, model="gen-model"):
    return RunConfig(
        condition=condition, split=Split.HELDOUT, git_commit="c" * 40, git_dirty=False,
        gold_set_sha256=SHA, manifest_sha256=SHA, llm_provider="gemini", llm_model=model,
        llm_base_url="https://x", llm_enabled=True, prompt_sha256=SHA, embedding_provider="e5",
        embedding_model="m", retrieval={"k": 5}, embedding_identity="e5:m",
        index_fingerprint=index, condition_settings=conditions.SETTINGS[Condition(condition)],
        batch_id=batch,
    )  # fmt: skip


def record(condition, metrics, **kw):
    return RunRecord(
        run_id=f"run-{condition}",
        started_at=datetime(2026, 11, 1, tzinfo=UTC),
        config=config(condition, **kw),
        corpus=CorpusSnapshot(course_code="BLM2512", documents=[]),
        items=[result()],
        metrics=metrics,
    )


# --- Temel çizgi hatları ---


def test_closed_book_sends_only_the_question():
    llm = FakeText("Bilmiyorum.")
    answer = closed_book("Ikili arama nedir?", "Veri Yapilari", llm)

    ((system, messages),) = llm.calls
    assert messages == [{"role": "user", "content": "Ikili arama nedir?"}]
    assert "Veri Yapilari" in system and "<sources>" not in messages[0]["content"]
    assert (answer.outcome, answer.text, answer.cited_source_ids) == ("answered", "Bilmiyorum.", [])
    assert answer.retrieved == []


def test_basic_rag_maps_labels_to_sources_without_verification():
    passages = [Passage(str(n), f"parca {n}") for n in range(1, 8)]
    llm = FakeText("Birinci [S2]. Uydurma [S9]. Yine [S2][S1].")
    answer = basic_rag("Soru?", "Ders", passages, llm)

    prompt = llm.calls[0][1][0]["content"]
    assert '<source label="S5">' in prompt and '<source label="S6">' not in prompt
    assert [p.source_id for p in answer.retrieved] == ["1", "2", "3", "4", "5"]
    # Bilinmeyen etiket yok sayılır; metin değiştirilmez (doğrulama yok).
    assert answer.cited_source_ids == ["2", "1"]
    assert answer.text == "Birinci [S2]. Uydurma [S9]. Yine [S2][S1]."


@pytest.mark.parametrize(
    ("error", "outcome"),
    [(LLMRefusal("x"), "model_refusal"), (LLMError("x"), "provider_failure")],
)
def test_baseline_failures_are_recorded_by_outcome(error, outcome):
    answer = closed_book("Soru?", "Ders", FakeText(error=error))
    assert (answer.outcome, answer.text) == (outcome, None)


def test_baselines_need_a_model():
    with pytest.raises(RuntimeError):
        closed_book("Soru?", "Ders", None)
    with pytest.raises(RuntimeError):
        basic_rag("Soru?", "Ders", [], None)


def test_every_condition_has_settings():
    assert set(conditions.SETTINGS) == set(Condition)
    assert conditions.SETTINGS[Condition.FULL_VIDEO_TIME]["playback_position"] is True


# --- Koşu ---


def test_parse_conditions():
    assert parse_conditions(["all"]) == list(Condition)
    assert parse_conditions(["full", "no_rag", "full"]) == [Condition.FULL, Condition.NO_RAG]


def test_no_rag_reports_retrieval_and_citation_as_not_applicable():
    metrics, _ = compute_metrics([gold()], [result()], Condition.NO_RAG)

    for name in ("retrieval_recall_at_5", "citation_presence_rate", "citation_precision"):
        assert metrics[name].value is None
        assert "no_rag" in (metrics[name].gap or "")
    assert metrics["out_of_scope_decline_rate"].gap  # kapsam dışı soru yok


def test_verification_failures_are_counted_separately():
    metrics, _ = compute_metrics(
        [gold("a"), gold("b")], [result("a", outcome="verification_failure"), result("b")]
    )
    assert metrics["verification_failure_rate"].value == 0.5
    assert metrics["provider_failure_rate"].value == 0.0


def test_full_video_time_gaps_for_items_without_playback():
    playback = Playback(document_sha256=SHA, time_s=30)
    assert condition_gaps(Condition.FULL, [gold()]) == []
    assert "Hiçbir soruda" in condition_gaps(Condition.FULL_VIDEO_TIME, [gold()])[0]
    gaps = condition_gaps(Condition.FULL_VIDEO_TIME, [gold("a", playback), gold("b")])
    assert gaps and gaps[0].startswith("1/2")
    assert condition_gaps(Condition.FULL_VIDEO_TIME, [gold("a", playback)]) == []


# --- Karşılaştırma ---


def test_comparison_lists_conditions_side_by_side(tmp_path):
    records = [
        record("no_rag", {"m": MetricValue(value=0.4, denominator=10)}),
        record("full", {"m": MetricValue(value=0.9, denominator=10)}),
    ]
    text = render_comparison(records)

    assert "| Metrik | no_rag | full |" in text
    assert "| m | 0.4 | 0.9 |" in text
    assert "Geçersiz" not in text
    path = write_comparison(records, tmp_path)
    assert path is not None and path.name == "b1.compare.md"
    with pytest.raises(FileExistsError):
        write_comparison(records, tmp_path)


def test_comparison_flags_uncontrolled_settings():
    records = [record("no_rag", {}, model="a"), record("full", {}, model="b")]
    assert "Geçersiz karşılaştırma" in render_comparison(records)


def test_single_condition_writes_no_comparison(tmp_path):
    assert write_comparison([record("full", {}, batch=None)], tmp_path) is None


# --- Gold set doğrulama ---


def test_playback_must_point_to_an_approved_video():
    from harness.schemas import CorpusManifest, GoldSet
    from harness.validate import structural_errors

    manifest = CorpusManifest(
        course_code="BLM2512",
        documents=[
            {"sha256": SHA, "title": "Notlar", "material_type": "notes", "status": "approved",
             "permission": "eğitmen onayı"},
        ],
    )  # fmt: skip

    def gold_set(item):
        return GoldSet(course_code="BLM2512", manifest="m.json", items=[item])

    ok = gold_set(gold("a", Playback(document_sha256=SHA, time_s=5)))
    bad = gold_set(gold("b", Playback(document_sha256="b" * 64, time_s=5)))

    assert structural_errors(ok, manifest) == []
    assert any("oynatma konumu" in e for e in structural_errors(bad, manifest))


def test_planned_full_set_gap():
    from harness.schemas import CorpusManifest, GoldSet
    from harness.validate import PLANNED_ANSWERABLE, set_gaps

    items = [gold(f"q{n}") for n in range(30)]
    gaps = set_gaps(
        GoldSet(course_code="BLM2512", manifest="m.json", items=items),
        CorpusManifest(course_code="BLM2512", documents=[]),
    )
    assert any(f"30/{PLANNED_ANSWERABLE}" in gap for gap in gaps)
