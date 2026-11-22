"""Yetkili görsel medya bağlamı ve saklama yaşam döngüsü (#25, ADR-11).

- İstek bağlamı: video varlığı, oynatma konumu ve kare kimliği doğrulanır, cevaba ve mesaj
  kaydına yazılır.
- Sınırlar: medya süresi, kare erişimi, kare silme.
- İşler: kare çıkarma ve yorumlama ayrı, kalıcı işlerdir; durum, iptal ve yeniden deneme.
- Saklama: medya yalnızca onu okuyan iş bitene kadar kalır; sahipsiz dosyalar temizlenir.

Gerçek veritabanı; transkriptör, kare çıkarma, OCR ve görsel yorumlayıcı sahtedir.
"""

import hashlib
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.db.models import Course, Document, Message, ProcessingJob, VideoFrame
from app.embeddings.fake import FakeEmbedder
from app.ingestion import frame_interpretation, lecture_frames, media
from app.ingestion.documents import frame_dir, media_duration_error
from app.ingestion.frame_interpretation import FrameContext, InterpretationError
from app.ingestion.frames import ExtractedFrame, FrameExtractionError
from app.jobs import retention
from app.jobs.queue import (
    CANCELLED_MESSAGE,
    INTERRUPTED_MESSAGE,
    UNEXPECTED_MESSAGE,
    cancel_job,
    enqueue,
    recover_stale,
)
from app.jobs.retention import sweep_storage
from app.jobs.worker import run_next, run_pending
from tests.conftest import enroll, make_user, make_vtt, session_factory
from tests.test_frames_db import SLIDES, frames_of
from tests.test_transcription import FakeTranscriber, course_files, refreshed, upload_media
from tests.test_video import LESSON, QUESTION, add_video, upload_vtt

MEDIA = b"\x00\x00\x00\x18ftypmp42" + b"\x07" * 64


@pytest.fixture
def transcriber(api, monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    return FakeTranscriber()


@pytest.fixture
def sessions(db_engine):
    return session_factory(db_engine)


@pytest.fixture
def frames_on(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """FRAME_EXTRACTION=ocr; kare çıkarma ve OCR sahte (SLIDES). Her çıkarma çağrısında medyanın
    diskte olup olmadığını kaydeder."""
    monkeypatch.setattr(settings, "frame_extraction", "ocr")
    media_seen: list[bool] = []

    def extract(media_path: Path, out_dir: Path, should_stop=lambda: False):
        media_seen.append(media_path.is_file())
        out_dir.mkdir(parents=True, exist_ok=True)
        extracted = []
        for ordinal, (t_start, t_end, _) in enumerate(SLIDES):
            image = out_dir / f"{ordinal}.png"
            image.write_bytes(b"\x89PNG kare " + str(ordinal).encode())
            extracted.append(
                ExtractedFrame(ordinal, t_start, t_end, min(t_start + 2.0, t_end), image)
            )
        return extracted

    results = {f"{ordinal}.png": result for ordinal, (_, _, result) in enumerate(SLIDES)}
    monkeypatch.setattr(lecture_frames, "extract_frames", extract)
    monkeypatch.setattr(lecture_frames, "read_image", lambda path, languages: results[path.name])
    monkeypatch.setattr(lecture_frames, "extractor_identity", lambda languages: "tesseract/test")
    # Kare işinin süre denetimi medyayı PyAV ile açar (CI'da yok); süre sahte.
    monkeypatch.setattr(media, "media_duration", lambda path: 705.0)
    return media_seen


class FakeInterpreter:
    identity = "fake-vlm/1"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, FrameContext]] = []

    def interpret(self, image_path: Path, context: FrameContext) -> str | None:
        self.calls.append((image_path.name, context))
        if self.error is not None:
            raise self.error
        # Yazısız kare (no_text) için güvenilir betimleme yok.
        return None if context.ocr_text is None else f"  Slayt: {context.ocr_text}  "


@pytest.fixture
def interpreter(monkeypatch: pytest.MonkeyPatch) -> FakeInterpreter:
    fake = FakeInterpreter()
    monkeypatch.setitem(frame_interpretation.INTERPRETERS, "fake", lambda: fake)
    monkeypatch.setattr(settings, "frame_interpreter", "fake")
    return fake


def run_all(db: Session, sessions, transcriber) -> int:
    db.commit()  # Testin oturumu açık işlem bırakmasın.
    return run_pending(sessions, transcriber, FakeEmbedder())


def run_one(db: Session, sessions, transcriber) -> bool:
    db.commit()
    return run_next(sessions, transcriber, FakeEmbedder())


def upload(client: TestClient, course: Course, name: str = "ders.mp4") -> int:
    response = upload_media(client, course.id, name=name, content=MEDIA, data={"title": "Ders 3"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def processed(client: TestClient, db: Session, course: Course, sessions, transcriber) -> Document:
    document_id = upload(client, course)
    run_all(db, sessions, transcriber)
    return refreshed(db, document_id)


def jobs_of(db: Session, document_id: int) -> list[ProcessingJob]:
    db.expire_all()
    return list(
        db.scalars(
            select(ProcessingJob)
            .where(ProcessingJob.document_id == document_id)
            .order_by(ProcessingJob.id)
        )
    )


def ask(client: TestClient, course: Course, **video) -> object:
    return client.post("/ask", json={"course_id": course.id, "question": QUESTION, "video": video})


def media_files(course: Course) -> list[Path]:
    return [path for path in course_files(course) if path.suffix == ".mp4"]


# --- istek bağlamı ve mesaj kaydı -------------------------------------------------------------


def test_ask_records_the_authorized_frame_of_the_paused_moment(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frames = frames_of(db, document)

    response = ask(client, course, document_id=document.id, time_s=200)

    assert response.status_code == 200, response.text
    context = response.json()["video_context"]
    assert context["document_id"] == document.id and context["time_s"] == 200
    assert context["media_sha256"] == hashlib.sha256(MEDIA).hexdigest()
    assert context["duration_s"] == 705.0
    # 200. saniyede ekrandaki kare: 190–410 aralığındaki üçüncü slayt.
    assert context["frame"]["frame_id"] == frames[2].id
    assert context["frame"]["image_url"].endswith(f"/frames/{frames[2].id}.png")
    meta = db.scalars(select(Message.meta).where(Message.role == "assistant")).one()
    # Kayıtta yalnızca kimlikler ve zamanlar var; görüntü ve OCR metni yok.
    assert meta["video"] == {
        "document_id": document.id,
        "media_sha256": hashlib.sha256(MEDIA).hexdigest(),
        "time_s": 200.0,
        "frame_id": frames[2].id,
        "frame": {"t_start": 190.0, "t_end": 410.0, "t_frame": 192.0},
    }


def test_selected_frame_must_belong_to_the_video_and_its_paused_moment(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    other = processed(client, db, course, sessions, transcriber)
    first = frames_of(db, document)[0]  # 0–90 sn
    foreign = frames_of(db, other)[0]

    # Oynatıcı ile kare zamanı arasındaki küçük fark kabul edilir.
    near = ask(client, course, document_id=document.id, time_s=90.5, frame_id=first.id)
    elsewhere = ask(client, course, document_id=document.id, time_s=300, frame_id=first.id)
    other_video = ask(client, course, document_id=document.id, time_s=10, frame_id=foreign.id)
    missing = ask(client, course, document_id=document.id, time_s=10, frame_id=2_000_000)

    assert near.status_code == 200
    assert near.json()["video_context"]["frame"]["frame_id"] == first.id
    for response in (elsewhere, other_video, missing):
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_frame"
    # Yalnızca kabul edilen istek kaydedildi (soru + cevap).
    assert len(db.scalars(select(Message)).all()) == 2


def test_video_of_another_course_and_non_finite_time_are_rejected(
    client: TestClient, db: Session, user, course: Course, api
) -> None:
    other_course = Course(code="BLM9999", name="Baska Ders", language="tr")
    db.add(other_course)
    db.commit()
    enroll(db, user, other_course, "instructor")
    foreign = add_video(db, other_course)
    own = add_video(db, course)

    foreign_response = ask(client, course, document_id=foreign.id, time_s=10)
    infinite = client.post(
        "/ask",
        content=(
            f'{{"course_id": {course.id}, "question": "q", '
            f'"video": {{"document_id": {own.id}, "time_s": 1e999}}}}'
        ),
        headers={"content-type": "application/json"},
    )

    assert foreign_response.status_code == 422
    assert foreign_response.json()["code"] == "invalid_video"
    # Sonsuz sayı reddedilir ve hata yanıtı yine JSON olarak yazılabilir (500 değil).
    assert infinite.status_code == 422
    assert infinite.json()["detail"][0]["loc"] == ["body", "video", "time_s"]
    assert infinite.json()["detail"][0]["input"] == "inf"
    assert db.scalars(select(Message)).all() == []


def test_subtitle_video_has_a_context_without_media_identity_or_frame(
    client: TestClient, db: Session, course: Course, api
) -> None:
    video = add_video(db, course)

    context = ask(client, course, document_id=video.id, time_s=1e6).json()["video_context"]

    assert context == {
        "document_id": video.id,
        "media_sha256": None,
        "duration_s": 705.0,
        "time_s": 705.0,  # süreye kırpıldı
        "frame": None,
    }


def test_tutor_turn_records_the_video_context(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frame = frames_of(db, document)[1]  # 90–190 sn

    response = client.post(
        "/tutor/turn",
        json={
            "course_id": course.id,
            "message": QUESTION,
            "video": {"document_id": document.id, "time_s": 120, "frame_id": frame.id},
        },
    )

    assert response.status_code == 200, response.text
    meta = db.scalars(select(Message.meta).where(Message.role == "assistant")).one()
    assert meta["video"]["frame_id"] == frame.id and meta["video"]["time_s"] == 120.0
    assert meta["video"]["media_sha256"] == hashlib.sha256(MEDIA).hexdigest()


# --- sınırlar ----------------------------------------------------------------------------------


def test_media_identity_is_recorded_at_upload(
    client: TestClient, db: Session, course: Course, transcriber
) -> None:
    response = upload_media(client, course.id, content=MEDIA)

    assert response.json()["media_sha256"] == hashlib.sha256(MEDIA).hexdigest()
    assert refreshed(db, response.json()["id"]).media_sha256 == hashlib.sha256(MEDIA).hexdigest()


def test_subtitles_longer_than_the_duration_limit_are_rejected(
    client: TestClient, db: Session, course: Course, api, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "max_media_duration_s", 600.0)

    response = upload_vtt(client, course.id, make_vtt(tmp_path / "uzun.vtt", LESSON))

    assert response.status_code == 422
    assert response.json()["detail"] == "Medya süresi 10 dakika sınırını aşıyor."
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


def test_media_longer_than_the_duration_limit_fails_without_frames(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "max_media_duration_s", 3600.0)
    transcriber.duration_s = 3600.5
    document_id = upload(client, course)

    run_all(db, sessions, transcriber)

    document = refreshed(db, document_id)
    assert (document.status, document.error) == ("failed", "Medya süresi 1 saat sınırını aşıyor.")
    assert [(job.kind, job.status) for job in jobs_of(db, document_id)] == [
        ("transcription", "failed")
    ]
    assert frames_on == [] and course_files(course) == []


def test_default_duration_limit_is_one_hour() -> None:
    """#125: transkripsiyonun belleği süreyle büyür (~3,7 GB/saat); varsayılan 1 saat güvenli."""
    assert Settings.model_fields["max_media_duration_s"].default == 3600
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "max_media_duration_s", 3600)
        assert media_duration_error(3600.0) is None
        assert media_duration_error(3600.5) == "Medya süresi 1 saat sınırını aşıyor."


# --- kare çıkarma işi: durum, iptal, yeniden deneme -------------------------------------------


def test_frames_are_extracted_by_a_separate_job_and_the_media_is_then_deleted(
    client: TestClient, client_for, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document_id = upload(client, course)

    assert run_one(db, sessions, transcriber)
    # Transkript hazır, doküman kareleri beklemeden öğrencilere açık; medya kare işine kaldı.
    assert refreshed(db, document_id).status == "ready"
    assert [(j.kind, j.status) for j in jobs_of(db, document_id)] == [
        ("transcription", "succeeded"),
        ("frames", "queued"),
    ]
    assert len(media_files(course)) == 1

    assert run_one(db, sessions, transcriber)
    assert frames_on == [True]  # medya kare işinde hâlâ diskteydi
    assert media_files(course) == []
    assert len(frames_of(db, refreshed(db, document_id))) == len(SLIDES)

    body = client.get(f"/documents/{document_id}/jobs").json()
    assert [(j["kind"], j["status"], j["attempts"]) for j in body] == [
        ("transcription", "succeeded", 1),
        ("frames", "succeeded", 1),
    ]
    assert body[1]["max_attempts"] == settings.job_max_attempts
    assert body[1]["cancel_requested"] is False and body[1]["finished_at"] is not None
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    outsider = make_user(db, "disaridan@example.com")
    assert client_for(student).get(f"/documents/{document_id}/jobs").status_code == 403
    assert client_for(outsider).get(f"/documents/{document_id}/jobs").status_code == 404


def test_audio_has_no_frame_job(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document_id = upload(client, course, name="ders.wav")

    assert run_all(db, sessions, transcriber) == 1

    assert [job.kind for job in jobs_of(db, document_id)] == ["transcription"]
    assert frames_on == [] and {p.suffix for p in course_files(course)} == {".vtt"}


def test_queued_frame_job_is_cancelled_and_the_document_stays_ready(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document_id = upload(client, course)
    run_one(db, sessions, transcriber)
    transcription, extraction = jobs_of(db, document_id)

    response = client.post(f"/documents/{document_id}/jobs/{extraction.id}/cancel")

    assert response.status_code == 200
    assert (response.json()["status"], response.json()["error"]) == ("cancelled", CANCELLED_MESSAGE)
    assert refreshed(db, document_id).status == "ready"
    assert media_files(course) == [] and run_all(db, sessions, transcriber) == 0
    assert frames_on == []
    for job in (extraction, transcription):
        again = client.post(f"/documents/{document_id}/jobs/{job.id}/cancel")
        assert again.status_code == 409 and again.json()["code"] == "job_not_active"
    # Doküman uç noktasında da iptal edilecek iş kalmadı.
    legacy = client.post(f"/documents/{document_id}/cancel")
    assert legacy.status_code == 409 and legacy.json()["code"] == "document_not_processing"


def test_job_of_another_document_is_not_found(
    client: TestClient, client_for, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    first = upload(client, course)
    second = upload(client, course)
    foreign_job = jobs_of(db, second)[0]

    response = client.post(f"/documents/{first}/jobs/{foreign_job.id}/cancel")

    assert response.status_code == 404 and response.json()["code"] == "job_not_found"
    assert jobs_of(db, second)[0].status == "queued"
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    # İşlenen doküman öğrenciye görünmez.
    denied = client_for(student).post(f"/documents/{second}/jobs/{foreign_job.id}/cancel")
    assert denied.status_code == 404


def test_running_frame_job_cancelled_midway_writes_no_frames(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def read(path, languages):
        with sessions() as other:
            job_id = other.scalar(select(ProcessingJob.id).where(ProcessingJob.kind == "frames"))
            cancel_job(other, job_id)
        return SLIDES[0][2]

    monkeypatch.setattr(lecture_frames, "read_image", read)
    document = processed(client, db, course, sessions, transcriber)

    extraction = jobs_of(db, document.id)[1]
    assert (extraction.status, extraction.cancel_requested) == ("cancelled", True)
    assert document.status == "ready" and frames_of(db, document) == []
    assert media_files(course) == []
    assert not frame_dir(course.id, document.id).exists()
    assert not frame_dir(course.id, document.id, staging=True).exists()


def test_failed_frame_job_reports_its_reason_and_deletes_the_media(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(*args, **kwargs):
        raise FrameExtractionError("Video kareleri çıkarılamadı.")

    monkeypatch.setattr(lecture_frames, "extract_frames", broken)
    document = processed(client, db, course, sessions, transcriber)

    extraction = jobs_of(db, document.id)[1]
    assert (extraction.status, extraction.attempts) == ("failed", 1)  # kalıcı: yeniden denenmez
    assert extraction.error == "Videodan slayt karesi çıkarılamadı."
    assert (document.status, document.error) == ("ready", None)
    assert media_files(course) == []


def test_unexpected_frame_error_is_retried_with_the_kept_media_then_fails(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[bool] = []

    def flaky(media_path: Path, out_dir: Path, should_stop=lambda: False):
        seen.append(media_path.is_file())
        raise RuntimeError("geçici hata")

    monkeypatch.setattr(lecture_frames, "extract_frames", flaky)
    document = processed(client, db, course, sessions, transcriber)

    extraction = jobs_of(db, document.id)[1]
    assert seen == [True] * settings.job_max_attempts
    assert (extraction.status, extraction.error) == ("failed", UNEXPECTED_MESSAGE)
    assert document.status == "ready" and media_files(course) == []


def test_stale_frame_job_is_requeued_or_failed_without_failing_the_document(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    retried = upload(client, course)
    abandoned = upload(client, course)
    run_one(db, sessions, transcriber)
    run_one(db, sessions, transcriber)
    for document_id, attempts in ((retried, 1), (abandoned, settings.job_max_attempts)):
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.document_id == document_id, ProcessingJob.kind == "frames")
            .values(
                status="running",
                attempts=attempts,
                heartbeat_at=func.now() - text("interval '1 hour'"),
            )
        )
    db.commit()

    with sessions() as other:
        assert recover_stale(other) == (1, 1)

    failed = jobs_of(db, abandoned)[1]
    assert (failed.status, failed.error) == ("failed", INTERRUPTED_MESSAGE)
    assert refreshed(db, abandoned).status == "ready"
    assert run_all(db, sessions, transcriber) == 1
    assert jobs_of(db, retried)[1].status == "succeeded"
    assert len(frames_of(db, refreshed(db, retried))) == len(SLIDES)
    assert media_files(course) == []


# --- kare yorumlama işi -------------------------------------------------------------------------


def test_interpretation_needs_a_configured_interpreter(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)

    response = client.post(f"/documents/{document.id}/frames/interpret")

    assert response.status_code == 409
    assert response.json()["code"] == "interpreter_not_configured"
    assert len(jobs_of(db, document.id)) == 2


def test_frames_are_interpreted_by_a_durable_job(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    interpreter: FakeInterpreter,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")

    queued = client.post(f"/documents/{document.id}/frames/interpret")
    duplicate = client.post(f"/documents/{document.id}/frames/interpret")
    denied = client_for(student).post(f"/documents/{document.id}/frames/interpret")

    assert queued.status_code == 202
    assert (queued.json()["kind"], queued.json()["status"]) == ("frame_interpretation", "queued")
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "job_already_active"
    assert denied.status_code == 403
    assert run_all(db, sessions, transcriber) == 1

    frames = frames_of(db, document)
    assert [frame.description_model for frame in frames] == ["fake-vlm/1"] * len(SLIDES)
    assert frames[0].description == "Slayt: Ikili Arama\nmid = (lo + hi) // 2"
    assert frames[4].description is None  # yazısız kare: betimleme uydurulmaz
    name, context = interpreter.calls[0]
    assert name == "0.png" and context.frame_id == frames[0].id
    assert "ikili arama" in context.transcript and context.language == "tr"
    listed = client_for(student).get(f"/documents/{document.id}/frames").json()
    assert listed[0]["description"] == frames[0].description
    assert listed[0]["description_model"] == "fake-vlm/1"
    # Biten yorumlama yeniden başlatılabilir.
    assert client.post(f"/documents/{document.id}/frames/interpret").status_code == 202


def test_cancelled_or_failed_interpretation_leaves_frames_untouched(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    interpreter: FakeInterpreter,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    job_id = client.post(f"/documents/{document.id}/frames/interpret").json()["id"]

    cancelled = client.post(f"/documents/{document.id}/jobs/{job_id}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert run_all(db, sessions, transcriber) == 0 and interpreter.calls == []

    interpreter.error = InterpretationError("Görsel model yüklenemedi.")
    assert client.post(f"/documents/{document.id}/frames/interpret").status_code == 202
    run_all(db, sessions, transcriber)

    failed = jobs_of(db, document.id)[-1]
    assert (failed.status, failed.error, failed.attempts) == (
        "failed",
        "Görsel model yüklenemedi.",
        1,
    )
    frames = frames_of(db, document)
    assert len(frames) == len(SLIDES)
    assert all(f.description is None and f.description_model is None for f in frames)
    assert refreshed(db, document.id).status == "ready"


def test_interpreter_never_reads_a_file_outside_the_frame_folder(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    interpreter: FakeInterpreter,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    (settings.upload_dir / "gizli.png").write_bytes(b"\x89PNG gizli")
    first = frames_of(db, document)[0]
    # Kayıttaki yol kare klasöründen dışarı çıkıyor (upload_dir/gizli.png).
    first.image_path = str(frame_dir(course.id, document.id) / ".." / ".." / ".." / "gizli.png")
    db.commit()

    client.post(f"/documents/{document.id}/frames/interpret")
    run_all(db, sessions, transcriber)

    assert "gizli.png" not in [name for name, _ in interpreter.calls]
    assert len(interpreter.calls) == len(SLIDES) - 1
    assert frames_of(db, document)[0].description_model is None


def test_video_without_frames_cannot_be_interpreted(
    client: TestClient, db: Session, course: Course, api, interpreter: FakeInterpreter
) -> None:
    video = add_video(db, course)

    response = client.post(f"/documents/{video.id}/frames/interpret")

    assert response.status_code == 409 and response.json()["code"] == "no_frames"


def test_frames_added_to_a_subtitle_video_set_its_media_identity(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    """#27 yolu: altyazıyla yüklenen videonun varlık kimliği karelerin geldiği medyadır."""
    video = add_video(db, course)
    assert video.media_sha256 is None

    response = client.post(f"/documents/{video.id}/frames", files={"file": ("ders.mp4", MEDIA)})
    assert response.status_code == 200, response.text
    run_all(db, sessions, transcriber)

    assert refreshed(db, video.id).media_sha256 == hashlib.sha256(MEDIA).hexdigest()
    assert [(job.kind, job.status) for job in jobs_of(db, video.id)] == [("frames", "succeeded")]


# --- kare erişimi ve silme ---------------------------------------------------------------------


def test_instructor_removes_a_single_frame_and_its_image(
    client: TestClient, client_for, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    other = processed(client, db, course, sessions, transcriber)
    frame = frames_of(db, document)[0]
    image = Path(frame.image_path)
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    path = f"/documents/{document.id}/frames/{frame.id}"

    assert client_for(student).delete(path).status_code == 403
    foreign = client.delete(f"/documents/{other.id}/frames/{frame.id}")
    assert foreign.status_code == 404 and foreign.json()["code"] == "frame_not_found"
    assert client.delete(path).status_code == 204

    assert not image.exists()
    assert frame.id not in [f.id for f in frames_of(db, document)]
    assert len(frames_of(db, document)) == len(SLIDES) - 1
    assert client.get(f"{path}.png").status_code == 404
    # Silinen kare artık istekte seçilemez.
    stale = ask(client, course, document_id=document.id, time_s=10, frame_id=frame.id)
    assert stale.status_code == 422 and stale.json()["code"] == "invalid_frame"
    assert len(frames_of(db, other)) == len(SLIDES)


def test_frame_citation_resolves_to_the_frame_for_members_only(
    client: TestClient, client_for, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frame = frames_of(db, document)[2]
    outsider = make_user(db, "disaridan@example.com")

    body = client.get(f"/sources/frame:{frame.id}").json()

    assert body["source_id"] == f"frame:{frame.id}"
    assert (body["document_id"], body["material_type"], body["page"]) == (
        document.id,
        "video",
        None,
    )
    assert (body["t_start"], body["t_end"]) == (190.0, 410.0)
    assert body["text"] == "Dijkstra\nKaynak Kuyruk Hedef"
    assert [f["frame_id"] for f in body["frames"]] == [frame.id]
    for source_id in (f"frame:{frame.id}", "frame:abc", "frame:99999999999", "frame:"):
        response = client_for(outsider).get(f"/sources/{source_id}")
        assert response.status_code == 404 and response.json()["code"] == "source_not_found"
    assert client.get("/sources/frame:2000000").status_code == 404


# --- saklama: sahipsiz dosyaların temizliği ---------------------------------------------------


def test_storage_sweep_removes_only_old_orphans(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 600.0)
    document = processed(client, db, course, sessions, transcriber)
    pending = upload(client, course)  # transkripsiyon işi kuyrukta: medyası etkin girdi
    root = settings.upload_dir / str(course.id)
    frames_root = root / "frames"

    orphan_media = root / "999999.mp4"  # dokümanı yok (çöken yüklemeden kaldı)
    leftover = root / f"{document.id}.mp4"  # hazır dokümanın, hiçbir işin girdisi olmayan medyası
    orphan_frames = frames_root / "999999"
    stale_staging = frames_root / f"{document.id}.partial"
    # #27: kareler için eklenen medya ve yeni kareler yazılırken kenara alınan eski kareler.
    added_media = root / f"{document.id}.frames.mp4"
    set_aside = frames_root / f"{document.id}.previous"
    huge_id = root / f"{2**40}.mp4"
    fresh = root / "888888.mp4"  # yeni: yazılmakta olan yükleme olabilir
    unrelated = root / "notlar.txt"
    for path in (orphan_media, leftover, added_media, huge_id, fresh, unrelated):
        path.write_bytes(b"x")
    for path in (orphan_frames, stale_staging, set_aside):
        path.mkdir(parents=True)
    active_input = root / f"{pending}.mp4"  # kuyruktaki transkripsiyonun medyası
    kept = [Path(document.file_path), frame_dir(course.id, document.id), active_input, unrelated]
    old = time.time() - 3600
    orphans = [
        orphan_media,
        leftover,
        added_media,
        orphan_frames,
        stale_staging,
        set_aside,
        huge_id,
    ]
    for path in [*orphans, *kept]:
        os.utime(path, (old, old))

    removed = sweep_storage(db)

    assert removed == len(orphans)
    for path in orphans:
        assert not path.exists(), path
    for path in (fresh, *kept):
        assert path.exists(), path
    assert len(frames_of(db, document)) == len(SLIDES)


def test_storage_sweep_keeps_the_staging_folder_of_a_running_frame_job(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 0.0)
    document_id = upload(client, course)
    run_one(db, sessions, transcriber)  # kare işi kuyrukta
    staging = frame_dir(course.id, document_id, staging=True)
    staging.mkdir(parents=True)
    old = time.time() - 60
    os.utime(staging, (old, old))
    os.utime(media_files(course)[0], (old, old))

    assert sweep_storage(db) == 0

    assert staging.exists() and len(media_files(course)) == 1
    assert db.scalar(select(func.count(VideoFrame.id))) == 0


def test_frame_media_over_the_duration_limit_fails_only_the_frame_job(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kısa altyazı + uzun video: altyazılı videoya eklenen medyanın süresi de sınırlıdır."""
    video = add_video(db, course)
    monkeypatch.setattr(media, "media_duration", lambda path: 3600 + 1.0)

    response = client.post(f"/documents/{video.id}/frames", files={"file": ("ders.mp4", MEDIA)})
    assert response.status_code == 200, response.text
    run_all(db, sessions, transcriber)

    (job,) = jobs_of(db, video.id)
    assert (job.kind, job.status, job.attempts) == ("frames", "failed", 1)
    assert job.error == "Medya süresi 1 saat sınırını aşıyor."
    assert frames_on == []  # kareler hiç çıkarılmadı
    document = refreshed(db, video.id)
    assert (document.status, document.media_sha256) == ("ready", None)
    assert media_files(course) == []


@pytest.mark.parametrize(
    ("probe", "message"),
    [
        (None, "Videonun süresi okunamadı."),
        (float("nan"), "Videonun süresi okunamadı."),
        (float("inf"), "Videonun süresi okunamadı."),
        (0.0, "Videonun süresi okunamadı."),
        (FrameExtractionError("Video dosyası açılamadı."), "Video dosyası açılamadı."),
    ],
)
def test_unreadable_frame_media_duration_is_a_controlled_failure(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
    probe,
    message: str,
) -> None:
    def duration(path: Path):
        if isinstance(probe, Exception):
            raise probe
        return probe

    monkeypatch.setattr(media, "media_duration", duration)
    document = processed(client, db, course, sessions, transcriber)

    frames_job = jobs_of(db, document.id)[1]
    assert (frames_job.status, frames_job.error, frames_job.attempts) == ("failed", message, 1)
    assert document.status == "ready" and frames_on == [] and media_files(course) == []


def test_storage_sweep_skips_an_orphan_replaced_after_the_scan(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Taramada eski ve sahipsiz görünen klasör silinmeden önce yeniden yaratıldı (yeni bir işin
    geçici klasörü gibi): eski karar yeni klasörü silmez."""
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 600.0)
    document = processed(client, db, course, sessions, transcriber)
    staging = frame_dir(course.id, document.id, staging=True)
    staging.mkdir(parents=True)
    old = time.time() - 3600
    os.utime(staging, (old, old))
    scan = retention._entries

    def scan_then_replace(root: Path):
        entries = scan(root)
        staging.rmdir()
        staging.mkdir()
        (staging / "0.png").write_bytes(b"\x89PNG yeni")
        return entries

    monkeypatch.setattr(retention, "_entries", scan_then_replace)

    assert sweep_storage(db) == 0
    assert (staging / "0.png").exists()


def test_storage_sweep_rechecks_jobs_enqueued_after_the_scan(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 600.0)
    document = processed(client, db, course, sessions, transcriber)
    root = settings.upload_dir / str(course.id)
    staging = frame_dir(course.id, document.id, staging=True)
    staging.mkdir(parents=True)
    added = root / f"{document.id}.frames.mp4"
    added.write_bytes(MEDIA)
    old = time.time() - 3600
    for path in (staging, added):
        os.utime(path, (old, old))
    scan = retention._entries

    def scan_then_enqueue(root: Path):
        entries = scan(root)
        with sessions() as other:
            enqueue(other, "frames", other.get(Document, document.id), added)
            other.commit()
        return entries

    monkeypatch.setattr(retention, "_entries", scan_then_enqueue)

    assert sweep_storage(db) == 0
    assert staging.exists() and added.exists()


def test_storage_sweep_skips_a_document_locked_by_another_transaction(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 600.0)
    document = processed(client, db, course, sessions, transcriber)
    leftover = settings.upload_dir / str(course.id) / f"{document.id}.mp4"
    leftover.write_bytes(b"x")
    old = time.time() - 3600
    os.utime(leftover, (old, old))

    with sessions() as other:
        other.execute(select(Document.id).where(Document.id == document.id).with_for_update())
        assert sweep_storage(db) == 0  # kilitli: bu turda dokunulmaz, beklenmez
        assert leftover.exists()
        other.rollback()

    assert sweep_storage(db) == 1
    assert not leftover.exists()


def test_storage_sweep_never_follows_symlinks_out_of_the_storage_root(
    db: Session, course: Course, api, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 0.0)
    outside = tmp_path / "outside"
    (outside / "frames" / "777").mkdir(parents=True)
    victim = outside / "555.mp4"
    victim.write_bytes(b"x")
    course_dir = settings.upload_dir / str(course.id)
    course_dir.mkdir(parents=True)
    try:
        # Bağlantı olan ders klasörü, `frames` klasörü ve aday dosya.
        (settings.upload_dir / "424242").symlink_to(outside, target_is_directory=True)
        (course_dir / "frames").symlink_to(outside / "frames", target_is_directory=True)
        (course_dir / "666.mp4").symlink_to(victim)
    except OSError:
        pytest.skip("Bu sistemde sembolik bağlantı oluşturulamıyor")
    old = time.time() - 3600
    for path in (victim, outside / "frames" / "777", outside):
        os.utime(path, (old, old))

    assert sweep_storage(db) == 0

    assert victim.exists() and (outside / "frames" / "777").is_dir()
    assert (course_dir / "666.mp4").is_symlink()
