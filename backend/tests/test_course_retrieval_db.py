"""#29: çok dersli arama ölçümü gerçek veritabanında (TEST_DATABASE_URL gerekir).

İki ders aynı notları, transkripti ve slayt yazısını taşır (`test_course_isolation.world`).
Ölçüm her dalı ve çapraz soruları koşar: hiçbir sonuç başka dersten gelmez, sorgu planları
yakalanır ve HNSW'ye kaymaz, parmak izleri yeniden hesaplanınca aynı kalır.
"""

import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, Document, VideoFrame
from app.retrieval.index import frame_inventory
from tests import test_course_isolation
from tests.conftest import BACKEND_DIR

# İki dersli dünya ve kare fikstürleri test_course_isolation'dan.
world = test_course_isolation.world
frames_on = test_course_isolation.frames_on
run_jobs = test_course_isolation.run_jobs
transcriber = test_course_isolation.transcriber

sys.path.insert(0, str(BACKEND_DIR.parent / "evaluation"))

from harness.corpus import Locator  # noqa: E402
from harness.course_retrieval import FRAMES, HYBRID, PLAYBACK, measure, render_markdown  # noqa: E402


def write_gold(db: Session, course: Course, video: Document, out: Path) -> Path:
    """Dersin bütün dokümanları onaylı envanter + iki taslak soru (not ve video/kare)."""
    locator = Locator(db, Path("."))
    documents = db.scalars(select(Document).where(Document.course_id == course.id)).all()
    shas = {document.id: locator.document_sha256(document) for document in documents}
    notes = next(d for d in documents if d.id != video.id)
    folder = out / course.code
    folder.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "course_code": course.code,
        "documents": [
            {
                "sha256": shas[d.id],
                "title": d.title,
                "material_type": d.material_type,
                "status": "approved",
                "permission": "test",
            }
            for d in documents
        ],
    }
    gold = {
        "schema_version": 1,
        "course_code": course.code,
        "manifest": "manifest.json",
        "items": [
            {
                "id": f"{course.code}-notes",
                "split": "calibration",
                "kind": "answerable",
                "question": "Neden sag yari elenir?",
                "reference_answer": "...",
                "evidence": [{"document_sha256": shas[notes.id], "page": 2}],
                "origin": "team_draft",
                "query_type": "concept",
            },
            {
                "id": f"{course.code}-slide",
                "split": "heldout",
                "kind": "answerable",
                "question": "Dijkstra kaynak kuyruk hedef",
                "reference_answer": "...",
                "evidence": [{"document_sha256": shas[video.id], "t_start": 0, "t_end": 1000}],
                "origin": "team_draft",
                "playback": {"document_sha256": shas[video.id], "time_s": 210},
                "visual": {"frame_kind": "diagram", "expected": "answer", "support": "mixed"},
            },
        ],
    }
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    path = folder / "gold_set.json"
    path.write_text(json.dumps(gold), encoding="utf-8")
    return path


def test_measurement_covers_every_branch_and_never_crosses_courses(
    db: Session, db_engine, world: SimpleNamespace, tmp_path: Path
) -> None:
    golds = [
        write_gold(db, world.a, world.video_a, tmp_path),
        write_gold(db, world.b, world.video_b, tmp_path),
    ]
    args = Namespace(
        gold=golds,
        split="all",
        files_root=Path("."),
        repo=tmp_path,
        database_url=db_engine.url.render_as_string(hide_password=False),
        include_unreviewed=True,
    )

    report = measure(args)

    assert [c["course_code"] for c in report["courses"]] == [world.a.code, world.b.code]
    for course in report["courses"]:
        branches = {b["branch"]: b for b in course["branches"]}
        assert branches[HYBRID]["items"] == 2 and branches[PLAYBACK]["items"] == 1
        assert branches[FRAMES]["items"] == 1  # kanıtı karesi olan videoda
        assert branches[PLAYBACK]["recall_at_5"] == 1.0
        assert branches[FRAMES]["recall_at_5"] == 1.0
        assert all(b["foreign_hits"] == 0 for b in course["branches"])
        assert course["index"]["frames"] > 0 and course["fingerprints"]["frames"]
        assert any("Taslak set" in gap for gap in course["gaps"])
        assert course["variants"][0]["name"] == "üretim"
    # Aynı slaytlar: iki dersin kare parmak izi aynı; notların başlığı farklı, metin indeksi ayrı.
    a, b = (c["fingerprints"] for c in report["courses"])
    assert a["frames"] == b["frames"] and a["index"] != b["index"]
    # Çapraz sorular: her soru öteki derste de sonuç bulur ama hiçbiri ders dışından değil.
    assert len(report["isolation"]) == 2
    for row in report["isolation"]:
        assert row["foreign_hits"] == 0 and row["branches_with_results"] > 0
    assert report["plans"] and not any(p["uses_vector_index"] for p in report["plans"])
    assert not any("İHLALİ" in gap for gap in report["gaps"])
    assert "## Ders filtresi" in render_markdown(report)


def test_frame_fingerprint_ignores_ids_and_changes_with_extraction(
    db: Session, world: SimpleNamespace
) -> None:
    before = frame_inventory(db, world.a.id)
    assert before.frames > 0 and before.extractors

    frame = db.scalars(
        select(VideoFrame).where(VideoFrame.course_id == world.a.id).order_by(VideoFrame.id)
    ).first()
    assert frame is not None
    # Kimlikten bağımsız: öteki dersteki aynı kareler aynı parmak izini verir.
    assert frame_inventory(db, world.b.id).fingerprint == before.fingerprint
    frame.extractor = "tesseract/9.9/eng"
    db.flush()
    assert frame_inventory(db, world.a.id).fingerprint != before.fingerprint
    db.rollback()
