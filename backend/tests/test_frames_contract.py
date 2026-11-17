"""Video kareleri sözleşmesi (CONTRACTS.md §4.1, #24, ADR-10): yalnızca tipler; davranış yok.

Veritabanı gerektiren testler TEST_DATABASE_URL yoksa atlanır.
"""

from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Course, Document, VideoFrame
from app.schemas.sources import FrameRef, SourceDetail
from tests.conftest import TEST_DATABASE_URL
from tests.test_flow import upload
from tests.test_video_contract import _alembic_config

FRAME = {
    "frame_id": 1,
    "document_id": 2,
    "t_start": 10.0,
    "t_end": 25.5,
    "t_frame": 11.0,
    "image_url": "/api/documents/2/frames/1.png",
    "status": "readable",
    "text": "T(n) = 2T(n/2) + n",
    "confidence": 0.91,
    "extractor": "tesseract/5.5.0/tur+eng",
}


def test_frame_ref_accepts_known_statuses_and_rejects_others() -> None:
    assert FrameRef(**FRAME).status == "readable"
    unreadable = FrameRef(**{**FRAME, "status": "unreadable", "text": None, "confidence": None})
    assert unreadable.text is None and unreadable.confidence is None
    with pytest.raises(ValidationError):
        FrameRef(**{**FRAME, "status": "blurry"})


def test_source_detail_frames_default_to_empty() -> None:
    detail = SourceDetail(
        source_id="1",
        course_id=1,
        document_id=2,
        document_title="Ders 1",
        material_type="video",
        text="metin",
    )

    assert detail.frames == []


def test_frame_extraction_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRAME_EXTRACTION", raising=False)
    assert Settings(_env_file=None).frame_extraction == "off"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, frame_extraction="vlm")


def test_source_detail_of_a_pdf_chunk_has_no_frames(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()
    chunk = client.get(f"/documents/{document['id']}/chunks").json()[0]

    assert client.get(f"/sources/{chunk['id']}").json()["frames"] == []


def _frame(document: Document, **overrides) -> VideoFrame:
    values = {
        "document_id": document.id,
        "course_id": document.course_id,
        "ordinal": 0,
        "t_start": 10.0,
        "t_end": 20.0,
        "t_frame": 11.0,
        "image_path": "frames/0.png",
        "status": "readable",
        "text": "metin",
        "confidence": 0.9,
        "extractor": "tesseract/test",
    }
    return VideoFrame(**{**values, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "blurry"},
        {"t_frame": 25.0},
        {"t_start": 30.0},
    ],
    ids=["unknown_status", "frame_after_interval", "start_after_end"],
)
def test_frame_table_rejects_inconsistent_rows(
    db: Session, client: TestClient, course: Course, sample_pdf: Path, overrides: dict
) -> None:
    document = db.get(Document, upload(client, course.id, sample_pdf).json()["id"])

    db.add(_frame(document, **overrides))
    with pytest.raises(IntegrityError):
        db.flush()


def test_frame_ordinal_is_unique_per_document_and_frames_go_with_the_document(
    db: Session, client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = db.get(Document, upload(client, course.id, sample_pdf).json()["id"])
    db.add(_frame(document))
    db.flush()

    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(_frame(document))
        db.flush()

    db.delete(document)
    db.flush()
    assert db.query(VideoFrame).count() == 0


def test_frames_migration_downgrades_and_upgrades(db_engine) -> None:
    assert TEST_DATABASE_URL
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    try:
        command.downgrade(config, "b3d8e1f4a2c7")
        assert "video_frames" not in inspect(db_engine).get_table_names()
    finally:
        command.upgrade(config, "head")
    inspector = inspect(db_engine)
    indexes = {index["name"] for index in inspector.get_indexes("video_frames")}
    assert {
        "ix_video_frames_course_id",
        "ix_video_frames_document_id_t_start",
        "ix_video_frames_search_vector",
        "ix_video_frames_embedding_hnsw",
    } <= indexes
