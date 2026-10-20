"""Video sözleşmesi (CONTRACTS.md §4, #14 PR a): yalnızca tipler; davranış yok.

Veritabanı gerektiren testler TEST_DATABASE_URL yoksa atlanır.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.db.models import Course
from app.retrieval.types import VideoPosition
from app.schemas.ask import AskRequest, VideoRef
from tests.conftest import BACKEND_DIR, TEST_DATABASE_URL
from tests.test_flow import upload


def test_ask_request_accepts_video_and_rejects_negative_time() -> None:
    request = AskRequest(
        course_id=1, question="Bu adım ne?", video={"document_id": 7, "time_s": 12.5}
    )

    assert request.video == VideoRef(document_id=7, time_s=12.5)
    assert AskRequest(course_id=1, question="Bu adım ne?").video is None
    assert VideoPosition(document_id=7, time_s=0).time_s == 0


def test_old_video_time_s_field_is_ignored() -> None:
    request = AskRequest.model_validate(
        {"course_id": 1, "question": "Bu adım ne?", "video_time_s": 30}
    )

    assert request.video is None
    assert not hasattr(request, "video_time_s")


def test_negative_video_time_is_rejected_by_api(client: TestClient, course: Course) -> None:
    response = client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": "Neden sag yari elenir?",
            "video": {"document_id": 1, "time_s": -1},
        },
    )

    assert response.status_code == 422


def test_old_video_time_s_request_is_answered_like_without_video(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    upload(client, course.id, sample_pdf)
    question = {"course_id": course.id, "question": "Neden sag yari elenir?"}

    plain = client.post("/ask", json=question)
    legacy = client.post("/ask", json={**question, "video_time_s": 90.0})

    assert plain.status_code == legacy.status_code == 200
    for key in ("answer", "outcome", "declined", "citations", "retrieval"):
        assert legacy.json()[key] == plain.json()[key], key


def test_pdf_document_cannot_be_sent_as_video(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()

    response = client.post(
        "/ask",
        json={
            "course_id": course.id,
            "question": "Neden sag yari elenir?",
            "video": {"document_id": document["id"], "time_s": 90.0},
        },
    )

    assert response.status_code == 422


def test_pdf_upload_has_no_video_fields(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    document = upload(client, course.id, sample_pdf).json()

    assert document["duration_s"] is None and document["media_url"] is None
    report = document["report"]
    assert report["duration_s"] is None
    assert report["cues_read"] is None and report["cues_skipped"] is None
    assert report["warnings"] == []
    listed = client.get(f"/courses/{course.id}/materials").json()[0]
    assert listed["duration_s"] is None and listed["media_url"] is None


def test_retrieval_hits_carry_time_fields_null_for_pdf(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    upload(client, course.id, sample_pdf)

    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    assert answer["retrieval"]
    for hit in answer["retrieval"]:
        assert "t_start" in hit and "t_end" in hit
        assert hit["t_start"] is None and hit["t_end"] is None


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def test_alembic_has_a_single_head() -> None:
    assert len(ScriptDirectory.from_config(_alembic_config()).get_heads()) == 1


def test_video_migration_downgrades_and_upgrades(db_engine) -> None:
    config = _alembic_config()
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    def video_schema() -> tuple[set[str], set[str]]:
        inspector = inspect(db_engine)
        columns = {c["name"] for c in inspector.get_columns("documents")}
        indexes = {i["name"] for i in inspector.get_indexes("chunks")}
        return columns, indexes

    try:
        command.downgrade(config, "5d2e8f1a9c37")
        columns, indexes = video_schema()
        assert not {"duration_s", "media_url"} & columns
        assert "ix_chunks_document_id_t_start" not in indexes
    finally:
        command.upgrade(config, "head")

    columns, indexes = video_schema()
    assert {"duration_s", "media_url"} <= columns
    assert "ix_chunks_document_id_t_start" in indexes
