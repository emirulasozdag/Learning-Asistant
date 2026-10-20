"""Altyazısız ders videosu/sesi: yerel transkripsiyon akışı (sahte transkriptör, gerçek DB).

TestClient'ta BackgroundTasks yanıt gönderildikten sonra, istek dönmeden önce çalışır; bu yüzden
upload çağrısı döndüğünde arka plan işi bitmiştir.
"""

import os
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document
from app.embeddings.fake import FakeEmbedder
from app.ingestion.media import INTERRUPTED_MESSAGE, fail_interrupted_documents, run_transcription
from app.ingestion.parsers.vtt_parser import parse_vtt, write_vtt
from app.ingestion.transcribe import Transcriber, TranscriptionError, get_transcriber
from app.ingestion.types import RawSegment
from app.main import app
from app.retrieval.hybrid import retrieve
from tests.conftest import enroll, make_user, make_vtt, session_factory
from tests.test_video import LESSON, add_video

SPEECH = [
    RawSegment(text=text, t_start=float(start), t_end=float(end)) for start, end, text in LESSON
]


class FakeTranscriber:
    identity = "fake/tiny/int8"

    def __init__(self, segments=SPEECH, duration_s=705.0, error: Exception | None = None) -> None:
        self.segments, self.duration_s, self.error = segments, duration_s, error
        self.calls: list[tuple[str, str]] = []

    def transcribe(self, path: Path, language: str):
        self.calls.append((path.suffix, language))
        assert path.is_file()
        if self.error:
            raise self.error
        return self.segments, self.duration_s, ["belirsiz bölüm"]


@pytest.fixture
def transcriber(api, monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    fake = FakeTranscriber()
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    app.dependency_overrides[get_transcriber] = lambda: fake
    return fake


def upload_media(client: TestClient, course_id: int, name: str = "ders.mp4", **kwargs):
    data = {"material_type": "video", "declaration": "true", **kwargs.pop("data", {})}
    content = kwargs.pop("content", b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64)
    return client.post(
        f"/courses/{course_id}/materials", data=data, files={"file": (name, content)}
    )


def course_files(course: Course) -> list[Path]:
    return list((settings.upload_dir / str(course.id)).glob("*"))


def refreshed(db: Session, document_id: int) -> Document:
    db.expire_all()
    return db.get(Document, document_id)


def unfinished(course: Course, user, status: str, **fields) -> Document:
    return Document(
        course_id=course.id,
        title=status,
        material_type="video",
        filename="a.mp4",
        file_path="",
        status=status,
        approved_by=user.id,
        approved_at=func.now(),
        **fields,
    )


def test_media_upload_is_processed_into_timed_chunks(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber
) -> None:
    response = upload_media(client, course.id, data={"title": "Ders 1"})

    assert response.status_code == 201
    body = response.json()
    assert (body["status"], body["chunk_count"], body["report"]) == ("processing", 0, None)
    assert body["material_type"] == "video"
    assert transcriber.calls == [(".mp4", "tr")]

    document = refreshed(db, body["id"])
    assert (document.status, document.error) == ("ready", None)
    assert document.transcript_source == "asr"
    assert document.transcript_model == "fake/tiny/int8"
    assert document.duration_s == 705.0
    assert document.approved_by is not None and document.approved_at is not None
    assert document.filename == "Ders 1.vtt"
    transcript = Path(document.file_path)
    assert transcript.suffix == ".vtt" and transcript.is_file()
    assert course_files(course) == [transcript]  # medya silindi
    assert [s.text for s in parse_vtt(transcript).segments] == [s.text for s in SPEECH]
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == document.id)).all()
    assert len(chunks) == len(LESSON)
    assert all(c.t_start is not None and c.t_end is not None and c.embedding_model for c in chunks)
    served = client.get(f"/documents/{document.id}/file")
    assert served.status_code == 200 and served.text.startswith("WEBVTT")


@pytest.mark.parametrize(
    ("error", "segments", "message"),
    [
        (RuntimeError("boom"), SPEECH, "Beklenmeyen bir hata oluştu."),
        (TranscriptionError("Medya dosyası çözülemedi."), SPEECH, "Medya dosyası çözülemedi."),
        (TranscriptionError("Transkripsiyon modeli yüklenemedi."), SPEECH, "modeli yüklenemedi"),
        (None, [], "Medyada konuşma bulunamadı."),
    ],
)
def test_failed_transcription_marks_document_failed_and_cleans_up(
    client: TestClient,
    db: Session,
    course: Course,
    transcriber: FakeTranscriber,
    error: Exception | None,
    segments: list[RawSegment],
    message: str,
) -> None:
    transcriber.error, transcriber.segments = error, segments

    response = upload_media(client, course.id)

    assert response.status_code == 201
    document = refreshed(db, response.json()["id"])
    assert document.status == "failed" and message in document.error
    assert db.scalar(select(func.count(Chunk.id))) == 0
    assert document.file_path == "" and document.transcript_source is None
    assert course_files(course) == []


def test_transcription_off_by_default_rejects_media(
    client: TestClient, db: Session, course: Course
) -> None:
    response = upload_media(client, course.id)

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "Bu sunucuda transkripsiyon kapalı; videonun altyazısını (.vtt) yükleyin."
    )
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


def test_vtt_still_works_when_transcription_is_off(
    client: TestClient, db: Session, course: Course, tmp_path: Path
) -> None:
    path = make_vtt(tmp_path / "ders.vtt", LESSON)
    with path.open("rb") as file:
        response = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "video", "declaration": "true"},
            files={"file": (path.name, file)},
        )

    body = response.json()
    assert response.status_code == 201 and body["status"] == "ready"
    assert (body["transcript_source"], body["transcript_model"]) == ("vtt", None)
    assert body["report"] is not None


@pytest.mark.parametrize("name", ["ders.avi", "ders.exe", "ders"])
def test_unsupported_extension_is_rejected(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber, name: str
) -> None:
    response = upload_media(client, course.id, name)

    assert response.status_code == 422
    assert db.scalars(select(Document)).all() == [] and transcriber.calls == []


@pytest.mark.parametrize("name", ["a.mp4", "a.webm", "a.mkv", "a.mov", "a.mp3", "a.m4a", "A.WAV"])
def test_all_media_extensions_are_accepted(
    client: TestClient, course: Course, transcriber: FakeTranscriber, name: str
) -> None:
    assert upload_media(client, course.id, name).status_code == 201
    assert transcriber.calls[-1][0] == Path(name).suffix.lower()


def test_media_over_the_size_limit_is_rejected_without_leftovers(
    client: TestClient,
    db: Session,
    course: Course,
    transcriber: FakeTranscriber,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "max_media_bytes", 1024)

    response = upload_media(client, course.id, content=b"\x00" * 1025)

    assert response.status_code == 422 and "sınırını aşıyor" in response.json()["detail"]
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []
    assert upload_media(client, course.id, content=b"\x00" * 1024).status_code == 201


def test_empty_media_is_rejected(
    client: TestClient, db: Session, course: Course, transcriber: FakeTranscriber
) -> None:
    response = upload_media(client, course.id, content=b"")

    assert response.status_code == 422
    assert db.scalars(select(Document)).all() == [] and course_files(course) == []


def test_media_url_must_be_https(
    client: TestClient, course: Course, transcriber: FakeTranscriber
) -> None:
    bad = upload_media(client, course.id, data={"media_url": "http://x.example/a"})
    assert bad.status_code == 422
    ok = upload_media(client, course.id, data={"media_url": "https://x.example/a"})
    assert ok.status_code == 201 and ok.json()["media_url"] == "https://x.example/a"


def test_only_the_instructor_can_upload_media(
    client_for, db: Session, course: Course, transcriber: FakeTranscriber
) -> None:
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")

    response = upload_media(client_for(student), course.id)

    assert response.status_code == 403
    assert db.scalars(select(Document)).all() == [] and transcriber.calls == []


def test_unfinished_documents_are_instructor_only_and_not_searchable(
    client_for, db: Session, user, course: Course
) -> None:
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    ready = add_video(db, course)
    processing = unfinished(course, user, "processing")
    failed = unfinished(course, user, "failed", error="Medya dosyası çözülemedi.")
    db.add_all([processing, failed])
    db.commit()

    path = f"/courses/{course.id}/materials"
    seen_by_student = client_for(student).get(path).json()
    seen_by_instructor = {d["id"]: d for d in client_for(user).get(path).json()}

    assert [d["id"] for d in seen_by_student] == [ready.id]
    assert set(seen_by_instructor) == {ready.id, processing.id, failed.id}
    assert seen_by_instructor[failed.id]["status"] == "failed"
    assert seen_by_instructor[failed.id]["error"] == "Medya dosyası çözülemedi."
    assert seen_by_instructor[ready.id]["transcript_source"] == "vtt"
    for hidden in (processing, failed):
        assert client_for(student).get(f"/documents/{hidden.id}/chunks").status_code == 404
        assert client_for(user).get(f"/documents/{hidden.id}/chunks").status_code == 200

    # Aramaya yalnızca hazır dokümanın parçaları girer (parçası olsa bile).
    question = "ikili arama dizi hedef"
    assert retrieve(db, course, question, k=10, embedder=FakeEmbedder()).passages
    ready.status = "processing"
    db.commit()
    assert retrieve(db, course, question, k=10, embedder=FakeEmbedder()).passages == []


def test_documents_stuck_in_processing_are_failed_on_startup(
    db: Session, db_engine, user, course: Course, api
) -> None:
    stuck = unfinished(course, user, "processing")
    done = add_video(db, course)
    db.add(stuck)
    db.commit()
    leftover = settings.upload_dir / str(course.id) / f"{stuck.id}.mp4"
    leftover.parent.mkdir(parents=True, exist_ok=True)
    leftover.write_bytes(b"x")

    assert fail_interrupted_documents(session_factory(db_engine)) == 1

    assert refreshed(db, stuck.id).status == "failed"
    assert refreshed(db, stuck.id).error == INTERRUPTED_MESSAGE
    assert refreshed(db, done.id).status == "ready"
    assert not leftover.exists()


def test_document_deleted_while_processing_leaves_nothing(
    db: Session, db_engine, tmp_path: Path
) -> None:
    media = tmp_path / "a.wav"
    media.write_bytes(b"x")

    run_transcription(session_factory(db_engine), 999, media, FakeTranscriber(), FakeEmbedder())

    assert not media.exists() and db.scalars(select(Chunk)).all() == []


def test_write_vtt_roundtrips_and_sanitizes(tmp_path: Path) -> None:
    path = tmp_path / "a.vtt"
    write_vtt(
        path,
        [
            RawSegment(text="birinci\n\nsatır --> x", t_start=0.0, t_end=3725.5),
            RawSegment(text="ikinci", t_start=3725.5, t_end=3730.0),
        ],
    )

    parsed = parse_vtt(path)
    assert [(s.text, s.t_start, s.t_end) for s in parsed.segments] == [
        ("birinci satır -> x", 0.0, 3725.5),
        ("ikinci", 3725.5, 3730.0),
    ]


def test_fake_transcriber_matches_protocol() -> None:
    transcriber: Transcriber = FakeTranscriber()
    assert transcriber.identity


def silent_wav(path: Path, seconds: int = 3) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(struct.pack("<h", 0) * 16000 * seconds)
    return path


@pytest.mark.skipif(not os.environ.get("RUN_ASR_TEST"), reason="RUN_ASR_TEST tanımlı değil")
def test_real_model_reports_no_speech_for_silence(
    db: Session, db_engine, user, course: Course, tmp_path: Path
) -> None:
    pytest.importorskip("faster_whisper")
    from app.ingestion.transcribe import FasterWhisperTranscriber

    document = unfinished(course, user, "processing")
    db.add(document)
    db.commit()
    media = silent_wav(tmp_path / "sessiz.wav")

    run_transcription(
        session_factory(db_engine),
        document.id,
        media,
        FasterWhisperTranscriber(os.environ.get("TRANSCRIPTION_MODEL") or "tiny"),
        FakeEmbedder(),
    )

    failed = refreshed(db, document.id)
    assert failed.status == "failed" and failed.error == "Medyada konuşma bulunamadı."
    assert not media.exists()
