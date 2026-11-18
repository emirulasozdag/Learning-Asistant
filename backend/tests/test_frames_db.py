"""Video kareleri: transkripsiyon işindeki kare adımı, saklama, erişim, kaynak gösterimi ve arama
(#24, ADR-10). Gerçek veritabanı; video çözme ve Tesseract sahtedir (CI'da yoktur).

Gerçek video + gerçek Tesseract ile uçtan uca: `test_frames_real.py`.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document, ProcessingJob, VideoFrame
from app.embeddings.fake import FakeEmbedder
from app.ingestion import lecture_frames
from app.ingestion.documents import frame_dir
from app.ingestion.frames import ExtractedFrame, FrameExtractionError
from app.ingestion.ocr import OcrError, OcrResult
from app.jobs.queue import JobCancelled
from app.jobs.worker import run_pending
from app.retrieval.frames import frame_search, frames_overlapping
from tests.conftest import enroll, make_user, session_factory
from tests.test_flow import upload
from tests.test_transcription import FakeTranscriber, course_files, refreshed, upload_media

# Konuşma (sahte transkript, test_video.LESSON): ikili arama 0–5 sn, ... Slaytlardaki yazı
# konuşmada geçmeyen bilgiyi de taşır (diyagram etiketi, formül).
SLIDES = [
    # (t_start, t_end, OCR sonucu)
    (0.0, 90.0, OcrResult("readable", "Ikili Arama\nmid = (lo + hi) // 2", 0.93)),
    (90.0, 190.0, OcrResult("partial", "Karsilastirma\nhedef < dizi[mid]", 0.71)),
    (190.0, 410.0, OcrResult("readable", "Dijkstra\nKaynak Kuyruk Hedef", 0.95)),
    (410.0, 500.0, OcrResult("unreadable", None, None)),
    (500.0, 705.0, OcrResult("no_text", None, None)),
]


@pytest.fixture
def transcriber(api, monkeypatch: pytest.MonkeyPatch) -> FakeTranscriber:
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    return FakeTranscriber()


@pytest.fixture
def run_jobs(db: Session, db_engine, transcriber: FakeTranscriber):
    def run() -> int:
        db.commit()  # Testin oturumu açık işlem bırakmasın.
        return run_pending(session_factory(db_engine), transcriber, FakeEmbedder())

    return run


@pytest.fixture
def frames_on(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """FRAME_EXTRACTION=ocr; kare çıkarma ve OCR sahte: SLIDES. Çıkarılan klasörleri döndürür."""
    monkeypatch.setattr(settings, "frame_extraction", "ocr")
    folders: list[Path] = []
    images = iter(())

    def extract(media_path: Path, out_dir: Path, should_stop=lambda: False):
        nonlocal images
        assert media_path.is_file()  # Medya kare adımında henüz silinmemiş olmalı.
        out_dir.mkdir(parents=True, exist_ok=True)
        folders.append(out_dir)
        extracted = []
        for ordinal, (t_start, t_end, _) in enumerate(SLIDES):
            image = out_dir / f"{ordinal}.png"
            image.write_bytes(b"\x89PNG kare " + str(ordinal).encode())
            extracted.append(
                ExtractedFrame(ordinal, t_start, t_end, min(t_start + 2.0, t_end), image)
            )
        images = iter(result for _, _, result in SLIDES)
        return extracted

    monkeypatch.setattr(lecture_frames, "extract_frames", extract)
    monkeypatch.setattr(lecture_frames, "read_image", lambda path, languages: next(images))
    monkeypatch.setattr(
        lecture_frames, "extractor_identity", lambda languages: f"tesseract/test/{languages}"
    )
    return folders


def processed_video(client: TestClient, db: Session, course: Course, run_jobs) -> Document:
    response = upload_media(client, course.id, data={"title": "Ders 3"})
    assert response.status_code == 201
    assert run_jobs() == 1
    return refreshed(db, response.json()["id"])


def frames_of(db: Session, document: Document) -> list[VideoFrame]:
    db.expire_all()
    return list(
        db.scalars(
            select(VideoFrame)
            .where(VideoFrame.document_id == document.id)
            .order_by(VideoFrame.ordinal)
        )
    )


# --- iş ve saklama -------------------------------------------------------------------------


def test_frames_are_extracted_read_and_stored_with_the_transcript(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)

    assert document.status == "ready"
    frames = frames_of(db, document)
    assert [(f.ordinal, f.t_start, f.t_end, f.status) for f in frames] == [
        (i, t_start, t_end, result.status) for i, (t_start, t_end, result) in enumerate(SLIDES)
    ]
    readable, partial, _, unreadable, no_text = frames
    assert readable.text == "Ikili Arama\nmid = (lo + hi) // 2" and readable.confidence == 0.93
    assert readable.extractor == "tesseract/test/tur+eng"
    for frame in (readable, partial, frames[2]):
        assert frame.embedding is not None and frame.embedding_model == FakeEmbedder().identity
        assert frame.search_vector is not None
    for frame in (unreadable, no_text):
        assert frame.text is None and frame.confidence is None
        assert frame.embedding is None and frame.embedding_model is None
        assert frame.search_vector is None
    # Görüntüler dokümanın kare klasöründe; geçici klasör ve medya silindi.
    images = frame_dir(course.id, document.id)
    assert [Path(f.image_path) for f in frames] == [images / f"{i}.png" for i in range(5)]
    assert all(Path(f.image_path).is_file() for f in frames)
    assert not frame_dir(course.id, document.id, staging=True).exists()
    assert {p.suffix for p in course_files(course) if p.is_file()} == {".vtt"}
    # Kareler parçalara (orijinal kanıt) karışmaz.
    chunk_texts = db.scalars(select(Chunk.text).where(Chunk.document_id == document.id)).all()
    assert not any("Kaynak" in text for text in chunk_texts)


def test_frame_times_never_pass_the_media_duration(
    client: TestClient,
    db: Session,
    course: Course,
    run_jobs,
    frames_on,
    transcriber: FakeTranscriber,
) -> None:
    transcriber.duration_s = 450.0

    frames = frames_of(db, processed_video(client, db, course, run_jobs))

    assert all(f.t_start <= f.t_frame <= f.t_end <= 450.0 for f in frames)


def test_frames_are_not_extracted_when_the_feature_is_off(
    client: TestClient, db: Session, course: Course, run_jobs, monkeypatch
) -> None:
    def must_not_run(*args, **kwargs):
        raise AssertionError("kare adımı kapalıyken çalıştı")

    monkeypatch.setattr(lecture_frames, "extract_frames", must_not_run)

    document = processed_video(client, db, course, run_jobs)

    assert document.status == "ready" and frames_of(db, document) == []


@pytest.mark.parametrize(
    "failure", [FrameExtractionError("Video kareleri çıkarılamadı."), OcrError("yok")]
)
def test_failed_frame_step_keeps_the_transcript(
    client: TestClient,
    db: Session,
    course: Course,
    run_jobs,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    def broken(*args, **kwargs):
        raise failure

    target = "extract_frames" if isinstance(failure, FrameExtractionError) else "extractor_identity"
    monkeypatch.setattr(lecture_frames, target, broken)

    document = processed_video(client, db, course, run_jobs)

    assert (document.status, document.error) == ("ready", None)
    assert frames_of(db, document) == []
    assert db.scalars(select(Chunk).where(Chunk.document_id == document.id)).first() is not None
    assert not frame_dir(course.id, document.id).exists()
    assert not frame_dir(course.id, document.id, staging=True).exists()


def test_one_frame_that_cannot_be_read_is_marked_unreadable(
    client: TestClient,
    db: Session,
    course: Course,
    run_jobs,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = iter([OcrError("zaman aşımı")] + [result for _, _, result in SLIDES[1:]])

    def read(path, languages):
        result = next(results)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(lecture_frames, "read_image", read)

    frames = frames_of(db, processed_video(client, db, course, run_jobs))

    assert [f.status for f in frames] == [
        "unreadable",
        "partial",
        "readable",
        "unreadable",
        "no_text",
    ]
    assert frames[0].text is None


def test_cancel_during_the_frame_step_writes_nothing(
    client: TestClient,
    db: Session,
    course: Course,
    run_jobs,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def cancelled(path, languages):
        raise JobCancelled("iptal")

    monkeypatch.setattr(lecture_frames, "read_image", cancelled)

    document = processed_video(client, db, course, run_jobs)

    assert document.status == "failed"
    assert db.scalar(select(ProcessingJob.status)) == "cancelled"
    assert frames_of(db, document) == []
    assert not frame_dir(course.id, document.id).exists()
    assert not frame_dir(course.id, document.id, staging=True).exists()
    leftovers = (settings.upload_dir / str(course.id)).rglob("*")
    assert [path for path in leftovers if path.is_file()] == []  # medya da silindi


def test_deleting_the_document_removes_frames_and_images(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)
    images = frame_dir(course.id, document.id)
    assert images.is_dir()

    assert client.delete(f"/documents/{document.id}").status_code == 204

    db.expire_all()
    assert db.scalars(select(VideoFrame)).all() == []
    assert not images.exists()


# --- API: liste, görüntü, erişim ---------------------------------------------------------------


def test_frames_are_listed_in_time_order_with_their_status(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)

    body = client.get(f"/documents/{document.id}/frames").json()

    assert [frame["status"] for frame in body] == [result.status for _, _, result in SLIDES]
    first = body[0]
    assert first["image_url"] == f"/api/documents/{document.id}/frames/{first['frame_id']}.png"
    assert first["text"] == "Ikili Arama\nmid = (lo + hi) // 2"
    assert (first["t_start"], first["t_end"], first["t_frame"]) == (0.0, 90.0, 2.0)
    assert body[3]["text"] is None and body[3]["confidence"] is None


def test_frame_image_is_served_to_members_only(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    run_jobs,
    frames_on,
) -> None:
    document = processed_video(client, db, course, run_jobs)
    frame = frames_of(db, document)[0]
    path = f"/documents/{document.id}/frames/{frame.id}.png"
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    outsider = make_user(db, "disaridan@example.com")

    served = client_for(student).get(path)

    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert served.headers["cache-control"] == "private, no-cache"
    assert served.content.startswith(b"\x89PNG kare 0")
    assert client_for(outsider).get(path).status_code == 404
    assert client_for(None).get(path).status_code == 401


def test_frame_of_another_document_or_missing_image_is_404(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on, sample_pdf
) -> None:
    document = processed_video(client, db, course, run_jobs)
    frame = frames_of(db, document)[0]
    pdf = upload(client, course.id, sample_pdf).json()

    assert client.get(f"/documents/{pdf['id']}/frames").json() == []
    assert client.get(f"/documents/{pdf['id']}/frames/{frame.id}.png").status_code == 404
    assert client.get(f"/documents/{document.id}/frames/999999.png").status_code == 404
    Path(frame.image_path).unlink()
    assert client.get(f"/documents/{document.id}/frames/{frame.id}.png").status_code == 404


def test_image_outside_the_frame_folder_is_not_served(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on, tmp_path
) -> None:
    document = processed_video(client, db, course, run_jobs)
    frame = frames_of(db, document)[0]
    elsewhere = tmp_path / "gizli.png"
    elsewhere.write_bytes(b"gizli")
    frame.image_path = str(elsewhere)
    db.commit()

    assert client.get(f"/documents/{document.id}/frames/{frame.id}.png").status_code == 404


# --- kaynak görüntüleyici ----------------------------------------------------------------------


def test_source_of_a_transcript_chunk_lists_frames_on_screen_during_it(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)
    chunks = db.scalars(
        select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.t_start)
    ).all()
    by_start = {chunk.t_start: chunk for chunk in chunks}

    # "ikili arama..." 0–5 sn: yalnızca ilk slayt ekranda.
    first = client.get(f"/sources/{by_start[0.0].id}").json()
    assert [frame["t_start"] for frame in first["frames"]] == [0.0]
    assert first["frames"][0]["text"].startswith("Ikili Arama")
    # 400–405 sn: Dijkstra slaytı (190–410) ekranda.
    middle = client.get(f"/sources/{by_start[400.0].id}").json()
    assert [frame["t_start"] for frame in middle["frames"]] == [190.0]


def test_frames_overlapping_ignores_frames_that_only_touch_the_interval(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)

    def starts(t_start: float, t_end: float) -> list[float]:
        return [f.t_start for f in frames_overlapping(db, document.id, t_start, t_end)]

    assert starts(80.0, 100.0) == [0.0, 90.0]
    assert starts(90.0, 100.0) == [90.0]  # 0–90 slaytı 90'da bitti
    assert starts(90.0, 90.0) == [90.0]  # anlık aralık: o anda ekrandaki
    assert starts(800.0, 900.0) == []


# --- arama -------------------------------------------------------------------------------------


def test_slide_text_absent_from_the_transcript_is_found_with_its_context(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    document = processed_video(client, db, course, run_jobs)
    transcript = " ".join(db.scalars(select(Chunk.text).where(Chunk.document_id == document.id)))
    assert "kuyruk" in transcript.lower() and "kaynak" not in transcript.lower()

    hits = frame_search(db, course, "Dijkstra kaynak", FakeEmbedder())

    assert hits and hits[0].frame.t_start == 190.0
    best = hits[0]
    assert best.document_title == "Ders 3" and best.lexical_rank == 1
    # Bağlam: aralıkta (190–410) konuşulanlar ve komşu kareler.
    assert [chunk.t_start for chunk in best.transcript] == [200.0, 300.0, 400.0]
    assert [frame.ordinal for frame in best.neighbors] == [1, 3]


def test_unreadable_frames_are_not_searched_and_course_isolation_holds(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on, user
) -> None:
    document = processed_video(client, db, course, run_jobs)
    other = Course(code="BLM9999", name="Baska ders", language="tr")
    db.add(other)
    db.commit()

    hits = frame_search(db, course, "mid hedef Kaynak", FakeEmbedder(), k=10)

    assert {hit.frame.status for hit in hits} == {"readable", "partial"}
    assert len(hits) == 3  # okunamayan ve yazısız kareler hiç aday olmaz
    assert frame_search(db, other, "Dijkstra kaynak", FakeEmbedder()) == []
    # Onayı kaldırılan dokümanın kareleri aranmaz.
    document.approved_at = None
    db.commit()
    assert frame_search(db, course, "Dijkstra kaynak", FakeEmbedder()) == []


def test_a_slide_that_needs_the_previous_one_comes_with_it_as_context(
    client: TestClient, db: Session, course: Course, run_jobs, frames_on
) -> None:
    processed_video(client, db, course, run_jobs)

    # İkinci slayt "hedef < dizi[mid]" der; `mid`in ne olduğu yalnızca ilk slaytta yazar.
    hits = frame_search(db, course, "karsilastirma hedef dizi", FakeEmbedder(), k=1)

    assert [hit.frame.ordinal for hit in hits] == [1]
    previous = hits[0].neighbors[0]
    assert previous.ordinal == 0 and "mid = (lo + hi) // 2" in (previous.text or "")
