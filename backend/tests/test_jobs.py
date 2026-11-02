"""Uzun işler (ADR-9) ve yükleme sınırları (#21): kuyruk, iptal, kurtarma, temizlik.

Gerçek veritabanı, sahte transkriptör. Testin kendi oturumu kuyruğu çalıştırmadan önce işlemini
kapatır (`run_jobs`); çalıştırıcı kendi oturumlarını açar.
"""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document, ProcessingJob
from app.embeddings.fake import FakeEmbedder
from app.jobs.queue import (
    CANCELLED_MESSAGE,
    INTERRUPTED_MESSAGE,
    JobCancelled,
    recover_stale,
    request_cancel,
)
from app.jobs.worker import run_pending
from tests.conftest import SAMPLE_PAGES, enroll, make_pdf, make_user, session_factory
from tests.test_transcription import (
    FakeTranscriber,
    course_files,
    refreshed,
    unfinished,
    upload_media,
)


@pytest.fixture
def transcriber(api, monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    return FakeTranscriber()


@pytest.fixture
def run_jobs(db: Session, db_engine):
    def run(transcriber) -> int:
        db.commit()
        return run_pending(session_factory(db_engine), transcriber, FakeEmbedder())

    return run


def job_for(db: Session, document_id: int) -> ProcessingJob:
    db.expire_all()
    return db.scalars(select(ProcessingJob).where(ProcessingJob.document_id == document_id)).one()


def make_stale(db: Session, job: ProcessingJob, attempts: int) -> None:
    db.execute(
        update(ProcessingJob)
        .where(ProcessingJob.id == job.id)
        .values(
            status="running",
            attempts=attempts,
            heartbeat_at=func.now() - text("interval '1 hour'"),
        )
    )
    db.commit()


def test_upload_writes_document_and_job_in_one_step(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber, run_jobs
) -> None:
    document_id = upload_media(client, course.id).json()["id"]

    job = job_for(db, document_id)
    assert (job.kind, job.status, job.attempts) == ("transcription", "queued", 0)
    assert Path(job.input_path).is_file()

    assert run_jobs(transcriber) == 1
    job = job_for(db, document_id)
    assert (job.status, job.attempts, job.error) == ("succeeded", 1, None)
    assert job.finished_at is not None and not Path(job.input_path).exists()
    assert run_jobs(transcriber) == 0


def test_transcription_runs_outside_an_open_transaction(
    client: TestClient, db: Session, db_engine, course: Course, transcriber: FakeTranscriber
) -> None:
    """Uzun adım sürerken hiçbir bağlantı "idle in transaction" beklemez (kilit/bağlantı tutmaz)."""
    seen: list[int] = []

    class Probe(FakeTranscriber):
        def transcribe(self, path: Path, language: str, should_stop=lambda: False):
            with db_engine.connect() as connection:
                seen.append(
                    connection.scalar(
                        text(
                            "SELECT count(*) FROM pg_stat_activity WHERE datname = "
                            "current_database() AND pid <> pg_backend_pid() "
                            "AND state LIKE 'idle in transaction%'"
                        )
                    )
                )
            return super().transcribe(path, language, should_stop)

    document_id = upload_media(client, course.id).json()["id"]
    db.commit()
    run_pending(session_factory(db_engine), Probe(), FakeEmbedder())

    assert seen == [0]
    assert refreshed(db, document_id).status == "ready"


def test_queued_job_is_cancelled_at_once(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber, run_jobs
) -> None:
    document_id = upload_media(client, course.id).json()["id"]

    response = client.post(f"/documents/{document_id}/cancel")

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["error"]) == ("failed", CANCELLED_MESSAGE)
    assert job_for(db, document_id).status == "cancelled"
    assert course_files(course) == []
    assert run_jobs(transcriber) == 0 and transcriber.calls == []
    again = client.post(f"/documents/{document_id}/cancel")
    assert again.status_code == 409 and again.json()["code"] == "document_not_processing"


def test_running_job_stops_when_cancelled(
    client: TestClient, db: Session, db_engine, course: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    """İptal çalışan işte canlılık kontrolüyle görülür; sonuç yazılmaz, dosyalar silinir."""
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    monkeypatch.setattr(settings, "job_heartbeat_interval_s", 0.01)
    sessions = session_factory(db_engine)

    class CancelledMidway(FakeTranscriber):
        def transcribe(self, path: Path, language: str, should_stop=lambda: False):
            with sessions() as other:
                assert request_cancel(other, other.get(Document, document_id))
            for _ in range(500):  # Gerçek transkriptör segment arasında yoklar.
                if should_stop():
                    raise JobCancelled(path.name)
                threading.Event().wait(0.01)
            raise AssertionError("iptal görülmedi")

    document_id = upload_media(client, course.id).json()["id"]
    db.commit()
    run_pending(sessions, CancelledMidway(), FakeEmbedder())

    document = refreshed(db, document_id)
    assert (document.status, document.error) == ("failed", CANCELLED_MESSAGE)
    assert job_for(db, document_id).status == "cancelled"
    assert db.scalar(select(func.count(Chunk.id))) == 0 and course_files(course) == []


def test_cancel_requested_after_transcription_discards_the_result(
    client: TestClient, db: Session, db_engine, course: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transkriptör iptali yoklamasa da sonuç yazılmadan önce iş satırı denetlenir."""
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    sessions = session_factory(db_engine)

    class IgnoresStop(FakeTranscriber):
        def transcribe(self, path: Path, language: str, should_stop=lambda: False):
            with sessions() as other:
                request_cancel(other, other.get(Document, document_id))
            return super().transcribe(path, language)

    document_id = upload_media(client, course.id).json()["id"]
    db.commit()
    run_pending(sessions, IgnoresStop(), FakeEmbedder())

    assert refreshed(db, document_id).status == "failed"
    assert db.scalar(select(func.count(Chunk.id))) == 0 and course_files(course) == []


def test_only_the_instructor_can_cancel(
    client: TestClient, client_for, db: Session, course: Course, transcriber: FakeTranscriber
) -> None:
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    document_id = upload_media(client, course.id).json()["id"]

    # İşlenen doküman öğrenciye görünmez: 404 (varlık sızdırılmaz).
    assert client_for(student).post(f"/documents/{document_id}/cancel").status_code == 404
    assert job_for(db, document_id).status == "queued"


def test_stale_job_is_requeued_and_finishes_with_its_kept_media(
    client: TestClient, db: Session, db_engine, course: Course, transcriber, run_jobs
) -> None:
    """Çalıştırıcı öldü (yeniden başlatma): medya diskte kaldığı için iş yeniden denenir."""
    document_id = upload_media(client, course.id).json()["id"]
    make_stale(db, job_for(db, document_id), attempts=1)

    with session_factory(db_engine)() as other:
        assert recover_stale(other) == (1, 0)

    job = job_for(db, document_id)
    assert (job.status, job.error) == ("queued", "Önceki deneme yarıda kaldı; yeniden deneniyor.")
    assert run_jobs(transcriber) == 1
    assert refreshed(db, document_id).status == "ready"
    assert job_for(db, document_id).attempts == 2


def test_stale_job_without_attempts_left_fails_and_cleans_up(
    client: TestClient, db: Session, db_engine, course: Course, transcriber
) -> None:
    document_id = upload_media(client, course.id).json()["id"]
    make_stale(db, job_for(db, document_id), attempts=settings.job_max_attempts)

    with session_factory(db_engine)() as other:
        assert recover_stale(other) == (0, 1)

    document = refreshed(db, document_id)
    assert (document.status, document.error) == ("failed", INTERRUPTED_MESSAGE)
    assert job_for(db, document_id).status == "failed"
    assert course_files(course) == []


def test_live_running_job_is_left_alone(
    client: TestClient, db: Session, db_engine, course: Course, transcriber
) -> None:
    """Başka bir çalıştırıcının sürdürdüğü (canlılığı taze) iş toparlanmaz."""
    document_id = upload_media(client, course.id).json()["id"]
    db.execute(update(ProcessingJob).values(status="running", attempts=1, heartbeat_at=func.now()))
    db.commit()

    with session_factory(db_engine)() as other:
        assert recover_stale(other) == (0, 0)
    assert job_for(db, document_id).status == "running"


def test_processing_document_without_a_job_is_failed(
    db: Session, db_engine, user, course: Course, api
) -> None:
    """ADR-9'dan önce yüklenip işleniyor kalmış doküman; artık medyası da silinir."""
    stuck = unfinished(course, user, "processing")
    db.add(stuck)
    db.commit()
    leftover = settings.upload_dir / str(course.id) / f"{stuck.id}.mp4"
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_bytes(b"x")

    with session_factory(db_engine)() as other:
        assert recover_stale(other) == (0, 1)

    assert refreshed(db, stuck.id).error == INTERRUPTED_MESSAGE
    assert not leftover.exists()


def test_unexpected_error_is_retried_then_fails(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber, run_jobs
) -> None:
    transcriber.error = RuntimeError("bağlantı koptu")
    document_id = upload_media(client, course.id).json()["id"]

    run_jobs(transcriber)

    assert len(transcriber.calls) == settings.job_max_attempts
    assert job_for(db, document_id).status == "failed"
    assert refreshed(db, document_id).error == "Beklenmeyen bir hata oluştu."
    assert course_files(course) == []


def test_deleting_a_processing_document_removes_job_and_media(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber, run_jobs
) -> None:
    document_id = upload_media(client, course.id).json()["id"]
    assert course_files(course) != []

    assert client.delete(f"/documents/{document_id}").status_code == 204

    assert db.scalars(select(ProcessingJob)).all() == []
    assert course_files(course) == []
    assert run_jobs(transcriber) == 0


def test_document_deleted_while_running_writes_nothing(
    client: TestClient, db: Session, db_engine, course: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    sessions = session_factory(db_engine)

    class DeletedMidway(FakeTranscriber):
        def transcribe(self, path: Path, language: str, should_stop=lambda: False):
            with sessions() as other:
                other.delete(other.get(Document, document_id))
                other.commit()
            return super().transcribe(path, language)

    document_id = upload_media(client, course.id).json()["id"]
    db.commit()
    run_pending(sessions, DeletedMidway(), FakeEmbedder())

    assert db.scalars(select(Chunk)).all() == [] and course_files(course) == []


def test_request_body_over_the_limit_is_rejected_before_it_is_read(
    client: TestClient, db: Session, course: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_media_bytes", 0)  # Sınır: yalnızca form payı (1 MB).

    response = upload_media(client, course.id, name="a.pdf", content=b"x" * (2 * 1024 * 1024))

    assert response.status_code == 413 and response.json()["code"] == "file_too_large"
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


def test_json_body_over_the_limit_is_rejected(
    client: TestClient, course: Course, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "max_request_bytes", 100)

    response = client.post("/ask", json={"course_id": course.id, "question": "a" * 200})

    assert response.status_code == 413 and response.json()["code"] == "file_too_large"


def test_document_over_its_size_limit_is_rejected(
    client: TestClient, db: Session, course: Course, tmp_path: Path, monkeypatch
) -> None:
    pdf = make_pdf(tmp_path / "notlar.pdf", SAMPLE_PAGES).read_bytes()
    monkeypatch.setattr("app.api.materials.MAX_UPLOAD_BYTES", len(pdf) - 1)

    response = client.post(
        f"/courses/{course.id}/materials",
        data={"material_type": "notes", "declaration": "true"},
        files={"file": ("notlar.pdf", pdf)},
    )

    assert response.status_code == 422 and "sınırını aşıyor" in response.json()["detail"]
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


@pytest.mark.parametrize(
    ("name", "title"),
    [("a" * 297 + ".pdf", None), ("notlar.pdf", "b" * 301)],
)
def test_overlong_filename_or_title_is_a_validation_error(
    client: TestClient, db: Session, course: Course, tmp_path: Path, name: str, title
) -> None:
    pdf = make_pdf(tmp_path / "notlar.pdf", SAMPLE_PAGES).read_bytes()
    data = {"material_type": "notes", "declaration": "true"}
    if title:
        data["title"] = title

    response = client.post(
        f"/courses/{course.id}/materials", data=data, files={"file": (name, pdf)}
    )

    assert response.status_code == 422 and "en fazla 300 karakter" in response.json()["detail"]
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


def test_deleting_a_document_removes_all_of_its_files(
    client: TestClient, db: Session, course: Course, tmp_path: Path
) -> None:
    pdf = make_pdf(tmp_path / "notlar.pdf", SAMPLE_PAGES)
    with pdf.open("rb") as file:
        document_id = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "notes", "declaration": "true"},
            files={"file": (pdf.name, file)},
        ).json()["id"]
    assert client.get(f"/documents/{document_id}/pages/1.png").status_code == 200
    stray = settings.upload_dir / str(course.id) / f"{document_id}.part"
    stray.write_bytes(b"x")

    assert client.delete(f"/documents/{document_id}").status_code == 204

    assert course_files(course) == []
    assert not (settings.cache_dir / "pages" / str(document_id)).exists()
