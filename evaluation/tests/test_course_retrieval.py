"""#29: çok dersli arama ölçümünün saf hesapları (veritabanısız).

Veritabanlı uçtan uca deneme: `backend/tests/test_course_retrieval_db.py`.
"""

from harness.course_retrieval import (
    FRAMES,
    HYBRID,
    Hit,
    duplicate_count,
    frame_alignment,
    pooled_variants,
    render_markdown,
    summarize_branch,
    summarize_plan,
)
from harness.schemas import GoldItem, QueryType, SourceLocator

VIDEO, NOTES = "a" * 64, "b" * 64


def item(id, evidence, query_type=None, visual=None, playback=None, split="heldout"):
    return GoldItem(
        id=id,
        split=split,
        kind="answerable",
        question=f"{id} nedir?",
        reference_answer="...",
        evidence=evidence,
        origin="team_draft",
        query_type=query_type,
        visual=visual,
        playback=playback,
    )


def page(n, sha=NOTES):
    return SourceLocator(document_sha256=sha, page=n)


def span(t_start, t_end, sha=VIDEO):
    return SourceLocator(document_sha256=sha, t_start=t_start, t_end=t_end)


def hit(source_id, locator, document_id=1, text=None):
    return Hit(source_id, document_id, locator, text or f"metin-{source_id}")


def test_retrieval_type_comes_from_query_type_then_frame_kind_then_concept() -> None:
    visual = {"frame_kind": "diagram", "expected": "answer", "support": "mixed"}
    playback = {"document_sha256": VIDEO, "time_s": 10}

    assert item("a", [page(1)], "code").retrieval_type is QueryType.CODE
    assert item("b", [span(0, 5)], visual=visual, playback=playback).retrieval_type is (
        QueryType.DIAGRAM
    )
    ambiguous = {**visual, "frame_kind": "ambiguous"}
    assert item("c", [span(0, 5)], visual=ambiguous, playback=playback).retrieval_type is (
        QueryType.CONCEPT
    )
    assert item("d", [page(1)]).retrieval_type is QueryType.CONCEPT


def test_duplicates_are_same_text_same_page_or_mostly_the_same_time_span() -> None:
    hits = [
        hit("1", page(3)),
        hit("2", page(3)),  # aynı sayfa
        hit("3", span(0, 60), document_id=2),
        hit("4", span(40, 100), document_id=2),  # 20 sn komşuluk (bilerek üst üste binme)
        hit("5", span(10, 50), document_id=2),  # kısa olanın tamamı 0–60 içinde
        hit("6", page(9), document_id=3, text="metin-1"),  # başka dokümanda aynı metin
    ]

    assert duplicate_count(hits, k=6) == 3
    assert duplicate_count(hits, k=2) == 1
    assert duplicate_count(hits[2:4]) == 0


def test_branch_summary_reports_recall_by_type_and_defects() -> None:
    items = [
        item("code-1", [page(2)], "code"),
        item("lex-1", [page(5)], "lexical"),
        item("concept-1", [span(100, 160)]),
    ]
    documents = {1, 2}
    hits = {
        "code-1": [hit("1", page(2)), hit("2", page(2))],  # bulundu, tekrar, kısa liste
        "lex-1": [hit(str(i), page(10 + i)) for i in range(5)],  # bulunamadı
        "concept-1": [hit("9", span(90, 120), document_id=2), hit("8", page(1), document_id=99)],
    }

    result = summarize_branch(HYBRID, items, hits, documents, searchable_units=100)

    assert result.items == 3
    assert result.recall_at_5 == round(2 / 3, 4)
    assert result.recall_by_type["code"] == 1.0
    assert result.recall_by_type["lexical"] == 0.0
    assert result.recall_by_type["concept"] == 1.0
    assert result.recall_by_type["diagram"] is None and result.items_by_type["diagram"] == 0
    assert result.first_hit_rank == {"code-1": 1, "lex-1": None, "concept-1": 1}
    assert result.short_lists == ["code-1", "concept-1"]
    assert result.duplicates == {"code-1": 1}
    assert result.foreign_hits == 1  # 99 dersin dokümanı değil


def test_short_list_is_not_starvation_when_the_course_has_fewer_units() -> None:
    items = [item("f-1", [span(0, 10)])]

    result = summarize_branch(FRAMES, items, {"f-1": [hit("1", span(0, 10))]}, {1}, 3)

    assert result.short_lists == [] and result.recall_at_5 == 1.0


def test_unasked_branch_has_no_recall() -> None:
    result = summarize_branch(FRAMES, [item("x", [page(1)])], {}, {1}, 100)

    assert result.items == 0 and result.recall_at_5 is None


def test_plan_summary_flags_vector_index_use() -> None:
    exact = {
        "Plan": {
            "Node Type": "Limit",
            "Actual Rows": 10,
            "Plans": [
                {"Node Type": "Sort", "Plans": [{"Node Type": "Seq Scan"}]},
                {"Node Type": "Index Scan", "Index Name": "ix_chunks_course_id"},
            ],
        },
        "Execution Time": 12.5,
    }
    approximate = {
        "Plan": {
            "Node Type": "Limit",
            "Plans": [{"Node Type": "Index Scan", "Index Name": "ix_chunks_embedding_hnsw"}],
        }
    }

    summary = summarize_plan("dense", exact)

    assert summary.node_types == ["Index Scan", "Limit", "Seq Scan", "Sort"]
    assert summary.indexes == ["ix_chunks_course_id"]
    assert summary.uses_vector_index is False
    assert (summary.execution_ms, summary.rows) == (12.5, 10)
    assert summarize_plan("dense", approximate).uses_vector_index is True


def test_frame_alignment_counts_degenerate_overlapping_and_contextless_frames() -> None:
    frames = [
        # (doküman, sıra, t_start, t_end, t_frame, durum)
        (1, 0, 0.0, 60.0, 2.0, "readable"),
        (1, 1, 50.0, 120.0, 52.0, "partial"),  # öncekiyle çakışıyor
        (1, 2, 200.0, 250.0, 202.0, "readable"),  # 80 sn boşluk; transkript yok
        (1, 3, 300.0, 300.0, 300.0, "readable"),  # sıfır uzunluk; süreyi de aşıyor
        (2, 0, 0.0, 10.0, 20.0, "no_text"),  # t_frame aralık dışında
    ]
    durations = {1: 290.0, 2: None}
    transcript = {1: [(0.0, 30.0), (30.0, 130.0)]}

    alignment = frame_alignment(frames, durations, transcript)

    assert alignment.frames == 5 and alignment.searchable == 4
    assert alignment.invalid_interval == 2
    assert alignment.beyond_duration == 1
    assert alignment.overlapping_neighbors == 1
    assert alignment.without_transcript == 2
    assert alignment.gap_total_s == 80.0 + 50.0


def test_pooled_variants_weight_by_question_count() -> None:
    def course(recall, items):
        return {"variants": [{"name": "üretim", "recall": recall, "items": items}]}

    first = course(
        {"calibration": 1.0, "heldout": 0.5, "all": 0.6},
        {"calibration": 1, "heldout": 4, "all": 5},
    )
    second = course(
        {"calibration": None, "heldout": 0.0, "all": 0.0},
        {"calibration": 0, "heldout": 5, "all": 5},
    )

    pooled = pooled_variants([first, second])

    assert pooled == {"üretim": {"calibration": 1.0, "heldout": round(2 / 9, 4), "all": 0.3}}


def test_markdown_report_names_fingerprints_isolation_and_gaps() -> None:
    branch = summarize_branch(HYBRID, [item("a", [page(1)])], {"a": [hit("1", page(1))]}, {1}, 9)
    from dataclasses import asdict

    report = {
        "report_id": "r1",
        "git_commit": "abc",
        "git_dirty": True,
        "split": "all",
        "recall_k": 5,
        "rank_depth": 50,
        "courses": [
            {
                "course_code": "6.006",
                "questions": 1,
                "fingerprints": {
                    "corpus": "c" * 64,
                    "embedding_identity": "fake/v1",
                    "index": "i" * 64,
                    "frames": "f" * 64,
                },
                "index": {
                    "documents": 2,
                    "chunks": 9,
                    "frames": 0,
                    "framed_videos": 0,
                    "frames_by_status": {},
                    "frame_extractors": [],
                    "frame_interpreters": [],
                },
                "branches": [asdict(branch)],
                "variants": [
                    {
                        "name": "üretim",
                        "params": {},
                        "recall": {"calibration": None, "heldout": 1.0, "all": 1.0},
                        "recall_playback": {"calibration": None, "heldout": None, "all": None},
                        "items": {"calibration": 0, "heldout": 1, "all": 1},
                    }
                ],
                "gate_refused": [],
                "frame_alignment": asdict(frame_alignment([], {}, {})),
                "gaps": ["Taslak set"],
            }
        ],
        "isolation": [
            {
                "questions_from": "6.006",
                "asked_in": "18.06",
                "questions": 1,
                "branches_with_results": 3,
                "foreign_hits": 0,
            }
        ],
        "plans": [],
        "gaps": ["Çalışma ağacında commit'lenmemiş değişiklik var"],
    }

    text = render_markdown(report)

    assert "## 6.006" in text and f"derlem `{'c' * 16}`" in text and f"kareler `{'f' * 16}`" in text
    assert "| hybrid | 1 | 1.00 |" in text
    assert "| 6.006 | 18.06 | 1 | 3 | 0 |" in text
    assert "| üretim | — (0) | 1.00 (1) | 1.00 (1) | — |" in text
    assert "Taslak set" in text and "commit'lenmemiş" in text
