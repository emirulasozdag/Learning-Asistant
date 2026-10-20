import json
from datetime import UTC, datetime

from harness.report import render_markdown
from harness.schemas import (
    CorpusManifest,
    CorpusSnapshot,
    GoldSet,
    MetricValue,
    RunConfig,
    RunRecord,
)
from harness.validate import find_problems, main

SHA_OK = "a" * 64
SHA_EXCL = "b" * 64
SHA_UNKNOWN = "c" * 64
REVIEW = {"reviewer": "instructor-1", "reviewed_at": "2026-10-01T10:00:00Z"}


def manifest_dict(course="BLM2512", approved_by=True):
    return {
        "course_code": course,
        "approved_by": REVIEW if approved_by else None,
        "documents": [
            {"sha256": SHA_OK, "title": "Ders 1", "material_type": "pdf",
             "status": "approved", "permission": "e-posta"},
            {"sha256": SHA_EXCL, "title": "Sınav", "material_type": "pdf",
             "status": "excluded", "exclusion_reason": "aktif sınav"},
        ],
    }  # fmt: skip


def item_dict(id, kind="answerable", split="heldout", question=None, **kw):
    data = {
        "id": id,
        "split": split,
        "kind": kind,
        "question": question or f"Soru {id}?",
        "origin": "instructor",
        "review": REVIEW,
    }
    if kind == "answerable":
        data["reference_answer"] = "cevap"
        data["evidence"] = [{"document_sha256": SHA_OK, "page": 1}]
    return {**data, **kw}


def gold_dict(*items, course="BLM2512"):
    return {"course_code": course, "manifest": "manifest.json", "items": list(items)}


def problems(*items, manifest=None):
    gold = GoldSet.model_validate(gold_dict(*items))
    return find_problems(gold, CorpusManifest.model_validate(manifest or manifest_dict()))


def has(found, text):
    return any(text in p for p in found)


def test_evidence_in_excluded_document():
    found = problems(item_dict("q", evidence=[{"document_sha256": SHA_EXCL}]))
    assert has(found, "q: kanıt dışlanmış")


def test_evidence_in_unknown_document():
    found = problems(item_dict("q", evidence=[{"document_sha256": SHA_UNKNOWN}]))
    assert has(found, "q: kanıt envanterde olmayan")


def test_answerable_missing_evidence_and_reference():
    found = problems(item_dict("q", evidence=[], reference_answer=None))
    assert has(found, "q: cevaplanabilir soruda gold kanıt yok")
    assert has(found, "q: referans cevap yok")


def test_same_question_in_both_splits():
    found = problems(
        item_dict("a", split="heldout", question="Aynı soru?"),
        item_dict("b", split="calibration", question="  aynı SORU? "),
    )
    assert has(found, "hem kalibrasyon hem held-out")
    assert has(found, "Aynı soru 2 kez")


def test_course_code_mismatch_and_manifest_gaps():
    found = problems(item_dict("a", split="calibration"), manifest=manifest_dict("XYZ100", False))
    assert has(found, "Ders kodu farklı")
    assert has(found, "Held-out soru yok")
    assert has(found, "approved_by boş")
    assert has(found, "0/30")


def test_clean_item_has_only_minimum_count_problems():
    found = problems(item_dict("a"))
    assert all("/30" in p for p in found) and len(found) == 2


# --- main --------------------------------------------------------------------------------------


def write(tmp_path, gold, manifest=None):
    (tmp_path / "manifest.json").write_text(json.dumps(manifest or manifest_dict()), "utf-8")
    path = tmp_path / "gold.json"
    path.write_text(json.dumps(gold), "utf-8")
    return str(path)


def test_main_invalid_schema_returns_1(tmp_path, capsys):
    gold = gold_dict(item_dict("q", kind="out_of_scope", evidence=[{"document_sha256": SHA_OK}]))
    assert main([write(tmp_path, gold)]) == 1
    assert "Geçersiz" in capsys.readouterr().err


def test_main_missing_file_returns_1(tmp_path):
    assert main([str(tmp_path / "yok.json")]) == 1


def test_main_with_problems_returns_0_and_strict_2(tmp_path, capsys):
    path = write(tmp_path, gold_dict(item_dict("q")))
    assert main([path]) == 0
    out = capsys.readouterr().out
    assert "BLM2512: 1 soru, 2 doküman" in out and "eksik:" in out
    assert main([path, "--strict"]) == 2


def test_main_explicit_manifest_option(tmp_path):
    path = write(tmp_path, gold_dict(item_dict("q")), manifest={"bad": 1})
    other = tmp_path / "other.json"
    other.write_text(json.dumps(manifest_dict()), "utf-8")
    assert main([path]) == 1
    assert main([path, "--manifest", str(other)]) == 0


# --- report ------------------------------------------------------------------------------------


def test_render_markdown_smoke():
    config = RunConfig(
        condition="full", split=None, git_commit=None, git_dirty=None,
        gold_set_sha256="a" * 64, manifest_sha256="b" * 64, llm_provider="p",
        llm_model=None, llm_base_url="https://x/v1", llm_enabled=False, prompt_sha256="c" * 64,
        embedding_provider="e", embedding_model="m", retrieval={"k": 5},
    )  # fmt: skip
    record = RunRecord(
        run_id="run1",
        started_at=datetime(2026, 10, 20, tzinfo=UTC),
        config=config,
        corpus=CorpusSnapshot(course_code="BLM2512", documents=[]),
        metrics={
            "m1": MetricValue(value=0.5, numerator=1, denominator=2),
            "m2": MetricValue(value=None, denominator=0, gap="neden yok"),
        },
        gaps=["bir boşluk"],
    )
    text = render_markdown(record)
    assert "`run1`" in text and "| m1 | 0.5 | 1/2 |" in text
    assert "neden yok" in text and "- bir boşluk" in text and "split: `all`" in text
