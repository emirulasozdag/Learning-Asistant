"""Değerlendirme harness'i gerçek soru-cevap hattı ve veritabanıyla (TEST_DATABASE_URL gerekir).

Harness birim testleri `evaluation/tests/` altında; burada yalnızca veritabanına dokunan kısım:
envanter karşılaştırması, kaynak konumu ve koşunun iz bırakmaması.
"""

import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Conversation, Course, Message
from tests.conftest import BACKEND_DIR
from tests.test_flow import upload

sys.path.insert(0, str(BACKEND_DIR.parent / "evaluation"))

from harness.corpus import Locator, snapshot  # noqa: E402
from harness.fingerprint import file_sha256  # noqa: E402
from harness.run import _backend_ask, compute_metrics, evaluate  # noqa: E402
from harness.schemas import (  # noqa: E402
    CorpusManifest,
    GoldItem,
    ManifestDocument,
    ManifestStatus,
    Review,
    SourceLocator,
)

REVIEW = Review(reviewer="instructor-1", reviewed_at=datetime(2026, 10, 20, tzinfo=UTC))


def manifest_for(*documents: ManifestDocument) -> CorpusManifest:
    return CorpusManifest(course_code="BLM2512", documents=list(documents))


def approved(path: Path) -> ManifestDocument:
    return ManifestDocument(
        sha256=file_sha256(path),
        title=path.stem,
        material_type="notes",
        status=ManifestStatus.APPROVED,
        permission="test",
    )


def test_baseline_run_locates_evidence_and_leaves_no_trace(
    client: TestClient, db: Session, db_engine, course: Course, sample_pdf: Path
) -> None:
    upload(client, course.id, sample_pdf)
    sha = file_sha256(sample_pdf)
    items = [
        GoldItem(
            id="q1",
            split="heldout",
            kind="answerable",
            question="Ikili aramada neden sag yari elenir?",
            reference_answer="Dizi sirali oldugu icin.",
            evidence=[SourceLocator(document_sha256=sha, page=2)],
            origin="instructor",
            review=REVIEW,
        ),
        GoldItem(
            id="q2",
            split="heldout",
            kind="out_of_scope",
            question="Fransa'nın başkenti neresi?",
            origin="instructor",
            review=REVIEW,
        ),
    ]
    locator = Locator(db, Path("."))

    corpus = snapshot(db, course, manifest_for(approved(sample_pdf)), locator)
    results = evaluate(items, _backend_ask(db_engine, course.id, None), locator.locate)
    metrics, _ = compute_metrics(items, results)

    assert corpus.unapproved_indexed == []
    assert corpus.documents[0].sha256 == sha
    answerable, out_of_scope = results
    assert answerable.error is None
    assert SourceLocator(document_sha256=sha, page=2) in answerable.retrieved
    # Judge'ın göreceği pasaj metni, konumla aynı sırada kaydedildi.
    assert len(answerable.retrieved_text) == len(answerable.retrieved)
    assert all(answerable.retrieved_text)
    assert out_of_scope.declined is True
    assert metrics["retrieval_recall_at_5"].value == 1.0
    assert metrics["out_of_scope_decline_rate"].value == 1.0
    # Her soru geri alınan bir işlemde soruldu: sohbet ve mesaj kalmadı.
    assert db.scalar(select(func.count(Message.id))) == 0
    assert db.scalar(select(func.count(Conversation.id))) == 0


def test_snapshot_flags_material_missing_from_manifest(
    client: TestClient, db: Session, course: Course, sample_pdf: Path, sample_pptx: Path
) -> None:
    upload(client, course.id, sample_pdf)
    excluded = approved(sample_pptx).model_copy(
        update={"status": ManifestStatus.EXCLUDED, "permission": None, "exclusion_reason": "x"}
    )

    corpus = snapshot(db, course, manifest_for(excluded), Locator(db, Path(".")))

    assert corpus.unapproved_indexed == ["notlar"]
    assert corpus.approved_not_indexed == []
