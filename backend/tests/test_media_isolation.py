"""Medya güvenilirliği, gizlilik ve ders izolasyonu (#31, S06-C).

#24 (kareler), #25 (görsel bağlam, kare işleri, saklama) ve #27'nin (kare videosu ekleme)
birleşik davranışını uçtan uca doğrular; tek tek durumlar `test_frames_db.py` ve
`test_visual_media.py`'dedir. Burada:

- Erişim matrisi: her medya/kare ucu × her rol (oturumsuz, ders dışı, başka dersin eğitmeni,
  üyeliği kaldırılmış öğrenci, öğrenci, TA, eğitmen). Okuma uçları üyelere, yönetim uçları
  eğitmene açık; üye olmayana 404 (varlık sızdırılmaz), rolü yetmeyene 403; yetkisiz istek hiçbir
  şeyi değiştirmez.
- Gizli doküman: onaysız, işlenen ya da başarısız videonun kareleri yalnızca eğitmene görünür.
- Bayat referans: video yenilenince ya da silinince eski kare kimlikleri, görüntü adresleri,
  alıntılar ve istekteki kare hiçbir şey sunmaz; soru kaydı yalnızca kimlik tutar.
- Disk ↔ veritabanı: her adımdan sonra diskte tam olarak veritabanının bildiği dosyalar vardır;
  medya, geçici klasör ya da sahipsiz görüntü kalmaz.
- Tekrar işleme: aynı medya iki kez yüklenirse iki bağımsız doküman olur; bir iş iki çalıştırıcıya
  verilmez; çalıştırıcı yeniden dönünce kare çoğalmaz.

Gerçek veritabanı; transkriptör, kare çıkarma ve OCR sahtedir (`test_visual_media.py`).
"""

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Document, Enrollment, Message, ProcessingJob, User, VideoFrame
from app.embeddings.fake import FakeEmbedder
from app.ingestion.documents import frame_dir
from app.jobs.queue import claim_next
from app.jobs.retention import sweep_storage
from app.retrieval.frames import FrameHit, frame_search
from tests import test_visual_media as vm
from tests.conftest import enroll, make_user, session_factory
from tests.test_frames_db import SLIDES, frames_of
from tests.test_transcription import refreshed

# `test_visual_media.py`'nin fikstürleri: sahte transkriptör, kare çıkarma/OCR, oturum üreticisi.
transcriber = vm.transcriber
sessions = vm.sessions
frames_on = vm.frames_on

MEDIA = vm.MEDIA
VIDEO_FILE = {"file": ("ders.mp4", MEDIA, "video/mp4")}


def processed(client: TestClient, db: Session, course: Course, sessions, transcriber) -> Document:
    return vm.processed(client, db, course, sessions, transcriber)


def job_count(db: Session) -> int:
    db.expire_all()
    return db.scalar(select(func.count(ProcessingJob.id))) or 0


def assert_status(response, expected: int, code: str | None, label: str) -> None:
    assert response.status_code == expected, f"{label}: {response.status_code} {response.text}"
    if code is not None:
        assert response.json()["code"] == code, f"{label}: {response.text}"


def other_course(db: Session) -> tuple[Course, User]:
    teacher = make_user(db, "baska-egitmen@example.com", can_create_courses=True)
    course = Course(code="BLM3021", name="Algoritma Analizi", language="tr")
    db.add(course)
    db.commit()
    enroll(db, teacher, course, "instructor")
    return course, teacher


def search(db: Session, course: Course, k: int = 5) -> list[FrameHit]:
    return frame_search(db, course, "Dijkstra Kaynak Kuyruk", FakeEmbedder(), k=k)


# --- erişim matrisi ----------------------------------------------------------------------------


def test_every_media_endpoint_follows_the_course_access_rules(
    client: TestClient,
    client_for: Callable[[User | None], TestClient],
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frame = frames_of(db, document)[2]
    job = vm.jobs_of(db, document.id)[-1]
    doc = f"/documents/{document.id}"

    _, foreign_teacher = other_course(db)
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    assistant = make_user(db, "asistan@example.com")
    enroll(db, assistant, course, "ta")
    revoked = make_user(db, "ayrilan@example.com")
    enroll(db, revoked, course, "student")
    revoked_client = client_for(revoked)
    # Üyelik kaldırılmadan önce görüntü açılıyordu; oturum açık kalır, erişim hemen biter.
    assert revoked_client.get(f"{doc}/frames/{frame.id}.png").status_code == 200
    db.execute(
        delete(Enrollment).where(
            Enrollment.user_id == revoked.id, Enrollment.course_id == course.id
        )
    )
    db.commit()

    reads: list[tuple[str, str, dict, str]] = [
        ("GET", f"{doc}/frames", {}, "document_not_found"),
        ("GET", f"{doc}/frames/{frame.id}.png", {}, "document_not_found"),
        ("GET", f"{doc}/file", {}, "document_not_found"),
        ("GET", f"{doc}/chunks", {}, "document_not_found"),
        ("GET", f"/sources/frame:{frame.id}", {}, "source_not_found"),
    ]
    manages: list[tuple[str, str, dict, str]] = [
        ("GET", f"{doc}/jobs", {}, "document_not_found"),
        ("POST", f"{doc}/jobs/{job.id}/cancel", {}, "document_not_found"),
        ("DELETE", f"{doc}/frames/{frame.id}", {}, "document_not_found"),
        ("POST", f"{doc}/frames", {"files": VIDEO_FILE}, "document_not_found"),
        ("POST", f"{doc}/frames/interpret", {}, "document_not_found"),
        ("POST", f"{doc}/cancel", {}, "document_not_found"),
        ("DELETE", doc, {}, "document_not_found"),
    ]
    # (istemci, okuma sonucu, yönetim sonucu); 404'ün kodu uca göre değişir.
    actors: dict[str, tuple[TestClient, int, int]] = {
        "oturumsuz": (client_for(None), 401, 401),
        "ders dışı": (client_for(make_user(db, "disaridan@example.com")), 404, 404),
        "başka dersin eğitmeni": (client_for(foreign_teacher), 404, 404),
        "üyeliği kaldırılan": (revoked_client, 404, 404),
        "öğrenci": (client_for(student), 200, 403),
        "TA": (client_for(assistant), 200, 403),
    }
    frames_before = len(frames_of(db, document))
    jobs_before = job_count(db)

    for actor, (actor_client, read_status, manage_status) in actors.items():
        for group, expected in ((reads, read_status), (manages, manage_status)):
            for method, path, kwargs, not_found in group:
                response = actor_client.request(method, path, **kwargs)
                code = {401: None, 403: "insufficient_role", 404: not_found}.get(expected)
                assert_status(response, expected, code, f"{actor} {method} {path}")

    # Yetkisiz isteklerin hiçbiri bir şey değiştirmedi.
    assert len(frames_of(db, document)) == frames_before
    assert job_count(db) == jobs_before
    assert Path(frame.image_path).is_file()
    assert refreshed(db, document.id).status == "ready"
    assert not vm.media_files(course)
    # Eğitmen için okuma uçları ve iş listesi açık.
    for _, path, _, _ in reads:
        assert client.get(path).status_code == 200, path
    assert client.get(f"{doc}/jobs").status_code == 200


def test_frames_of_a_hidden_video_are_visible_to_the_instructor_only(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frame = frames_of(db, document)[2]
    student = client_for(enroll_student(db, course))
    doc = f"/documents/{document.id}"
    paths = [
        f"{doc}/frames",
        f"{doc}/frames/{frame.id}.png",
        f"{doc}/file",
        f"/sources/frame:{frame.id}",
    ]
    assert all(student.get(path).status_code == 200 for path in paths)

    for hide in ("onaysız", "işleniyor", "başarısız"):
        stored = refreshed(db, document.id)
        if hide == "onaysız":
            stored.approved_at, approved_at = None, stored.approved_at
        else:
            stored.status = {"işleniyor": "processing", "başarısız": "failed"}[hide]
        db.commit()

        for path in paths:
            response = student.get(path)
            assert response.status_code == 404, f"{hide} {path}: {response.text}"
            assert client.get(path).status_code == 200, f"{hide} eğitmen {path}"
        asked = vm.ask(student, course, document_id=document.id, time_s=200, frame_id=frame.id)
        assert_status(asked, 422, "invalid_video", f"{hide} /ask")
        # Gizli videonun karesi aramaya da girmez.
        assert search(db, course, k=5) == []

        stored = refreshed(db, document.id)
        if hide == "onaysız":
            stored.approved_at = approved_at
        stored.status = "ready"
        db.commit()

    assert [hit.frame.id for hit in search(db, course, k=1)] == [frame.id]


def enroll_student(db: Session, course: Course, email: str = "ogrenci@example.com") -> User:
    student = make_user(db, email)
    enroll(db, student, course, "student")
    return student


def test_frames_never_cross_courses(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
) -> None:
    ours = processed(client, db, course, sessions, transcriber)
    foreign_course, foreign_teacher = other_course(db)
    teacher = client_for(foreign_teacher)
    theirs_id = vm.upload(teacher, foreign_course)
    vm.run_all(db, sessions, transcriber)
    theirs = refreshed(db, theirs_id)
    our_frame, their_frame = frames_of(db, ours)[2], frames_of(db, theirs)[2]
    their_job = vm.jobs_of(db, theirs.id)[-1]
    # Aynı medya iki derste: kimlik (özet) aynı, kareler ve dosyalar ayrı.
    assert ours.media_sha256 == theirs.media_sha256
    assert our_frame.id != their_frame.id

    # Bizim dokümanımızın yolu üzerinden onların karesi, işi ve görüntüsü bulunmaz.
    doc = f"/documents/{ours.id}"
    assert client.get(f"{doc}/frames/{their_frame.id}.png").status_code == 404
    assert_status(
        client.delete(f"{doc}/frames/{their_frame.id}"), 404, "frame_not_found", "kare sil"
    )
    assert_status(
        client.post(f"{doc}/jobs/{their_job.id}/cancel"), 404, "job_not_found", "iş iptal"
    )
    # Bizim dersimizdeki soruya onların videosu ya da karesi bağlam olamaz.
    assert_status(
        vm.ask(client, course, document_id=theirs.id, time_s=200), 422, "invalid_video", "video"
    )
    assert_status(
        vm.ask(client, course, document_id=ours.id, time_s=200, frame_id=their_frame.id),
        422,
        "invalid_frame",
        "kare",
    )
    # Arama yalnızca dersin kendi karelerini döndürür.
    hits = search(db, course, k=10)
    assert {hit.frame.document_id for hit in hits} == {ours.id}
    # Görüntüler kendi derslerinin klasöründe; birinin silinmesi ötekini etkilemez.
    assert Path(their_frame.image_path).is_relative_to(frame_dir(foreign_course.id, theirs.id))
    assert client.delete(doc).status_code == 204
    assert Path(their_frame.image_path).is_file()
    assert teacher.get(f"/documents/{theirs.id}/frames/{their_frame.id}.png").status_code == 200


# --- bayat referanslar -------------------------------------------------------------------------


def test_replaced_video_leaves_no_reachable_old_frame(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    old_ids = [frame.id for frame in frames_of(db, document)]
    old_id = old_ids[2]
    asked = vm.ask(client, course, document_id=document.id, time_s=200, frame_id=old_id)
    assert asked.status_code == 200, asked.text

    added = client.post(f"/documents/{document.id}/frames", files=VIDEO_FILE)
    assert added.status_code == 200, added.text
    vm.run_all(db, sessions, transcriber)

    new_ids = [frame.id for frame in frames_of(db, document)]
    assert len(new_ids) == len(SLIDES)
    assert not set(old_ids) & set(new_ids)
    student = client_for(enroll_student(db, course))
    for frame_id in old_ids:
        image = student.get(f"/documents/{document.id}/frames/{frame_id}.png")
        assert image.status_code == 404, frame_id
        assert_status(student.get(f"/sources/frame:{frame_id}"), 404, "source_not_found", "alıntı")
    stale = vm.ask(client, course, document_id=document.id, time_s=200, frame_id=old_id)
    assert_status(stale, 422, "invalid_frame", "eski kare")
    # Kayıtta eski kimlik kalır (bilerek, ADR-11); görüntü ya da metin kopyalanmadı.
    meta = db.scalars(select(Message.meta).where(Message.role == "assistant")).first()
    assert meta["video"]["frame_id"] == old_id
    assert "text" not in meta["video"] and "image_url" not in str(meta["video"])
    assert_inventory_matches(db, course)


def test_deleted_video_leaves_no_reachable_asset_or_file(
    client: TestClient,
    client_for,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frames = frames_of(db, document)
    student = client_for(enroll_student(db, course))
    asked = vm.ask(student, course, document_id=document.id, time_s=200)
    assert asked.status_code == 200, asked.text
    doc = f"/documents/{document.id}"

    assert client.delete(doc).status_code == 204

    for path in (f"{doc}/frames", f"{doc}/file", f"{doc}/chunks"):
        assert_status(student.get(path), 404, "document_not_found", path)
        assert_status(client.get(path), 404, "document_not_found", f"eğitmen {path}")
    for frame in frames:
        assert student.get(f"{doc}/frames/{frame.id}.png").status_code == 404
        assert_status(student.get(f"/sources/frame:{frame.id}"), 404, "source_not_found", "kare")
    assert_status(
        vm.ask(student, course, document_id=document.id, time_s=200),
        422,
        "invalid_video",
        "silinen video",
    )
    assert search(db, course, k=5) == []
    assert db.scalar(select(func.count(VideoFrame.id))) == 0
    assert db.scalar(select(func.count(ProcessingJob.id))) == 0
    # Diskte bu dokümana ait hiçbir şey kalmadı.
    assert not [path for path in course_tree(course) if path.name.split(".")[0] == str(document.id)]
    # Öğrencinin soru kaydı kalır; yalnızca kimlik ve zaman tutar, dosyaya işaret etmez.
    meta = db.scalars(select(Message.meta).where(Message.role == "assistant")).one()
    assert meta["video"]["document_id"] == document.id
    assert set(meta["video"]) == {"document_id", "media_sha256", "time_s", "frame_id", "frame"}


# --- disk ↔ veritabanı -------------------------------------------------------------------------


def course_tree(course: Course) -> list[Path]:
    root = settings.upload_dir / str(course.id)
    return sorted(root.rglob("*")) if root.exists() else []


def assert_inventory_matches(db: Session, course: Course) -> None:
    """Dersin klasöründe tam olarak veritabanının bildiği dosyalar var: dokümanların dosyası
    (etkin işin girdisi olan medya dahil) ve kare görüntüleri. Geçici klasör, sahipsiz görüntü
    ya da artık medya yok."""
    db.expire_all()
    documents = list(db.scalars(select(Document).where(Document.course_id == course.id)))
    expected = {Path(document.file_path) for document in documents if document.file_path}
    expected |= {
        Path(job.input_path)
        for job in db.scalars(
            select(ProcessingJob).where(ProcessingJob.status.in_(("queued", "running")))
        )
        if Path(job.input_path).is_file()
    }
    for document in documents:
        expected |= {Path(frame.image_path) for frame in frames_of(db, document)}
    files = {path for path in course_tree(course) if path.is_file()}
    folders = {path.name for path in course_tree(course) if path.is_dir()}
    assert files == expected, f"fazla: {files - expected}, eksik: {expected - files}"
    assert not [name for name in folders if name.endswith((".partial", ".previous"))]
    for path in expected:
        assert path.resolve().is_relative_to(settings.upload_dir.resolve()), path


def test_every_lifecycle_step_keeps_disk_and_database_in_step(
    client: TestClient,
    db: Session,
    course: Course,
    sessions,
    transcriber,
    frames_on,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document_id = vm.upload(client, course)
    assert_inventory_matches(db, course)  # medya, kuyruktaki işin girdisi

    assert vm.run_one(db, sessions, transcriber)  # transkripsiyon; kare işi medyayı devralır
    assert_inventory_matches(db, course)
    assert vm.media_files(course)

    vm.run_all(db, sessions, transcriber)  # kare işi; medya silinir
    assert_inventory_matches(db, course)
    assert not vm.media_files(course)
    frames = frames_of(db, refreshed(db, document_id))
    assert len(frames) == len(SLIDES)

    assert client.delete(f"/documents/{document_id}/frames/{frames[0].id}").status_code == 204
    assert_inventory_matches(db, course)

    assert client.post(f"/documents/{document_id}/frames", files=VIDEO_FILE).status_code == 200
    assert_inventory_matches(db, course)  # eklenen medya kare işinin girdisi
    vm.run_all(db, sessions, transcriber)
    assert_inventory_matches(db, course)
    assert len(frames_of(db, refreshed(db, document_id))) == len(SLIDES)

    cancelled = vm.upload(client, course)
    assert client.post(f"/documents/{cancelled}/cancel").status_code == 200
    assert_inventory_matches(db, course)  # iptal edilen yüklemenin medyası silindi

    # Temizlik tutarlı bir depoda hiçbir şey silmez.
    monkeypatch.setattr(settings, "storage_orphan_grace_s", 0.0)
    assert sweep_storage(db) == 0
    assert_inventory_matches(db, course)

    assert client.delete(f"/documents/{document_id}").status_code == 204
    assert client.delete(f"/documents/{cancelled}").status_code == 204
    assert_inventory_matches(db, course)
    assert not [path for path in course_tree(course) if path.is_file()]


# --- tekrar işleme -----------------------------------------------------------------------------


def test_same_media_uploaded_twice_gives_two_independent_videos(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    first = processed(client, db, course, sessions, transcriber)
    second = processed(client, db, course, sessions, transcriber)

    digest = hashlib.sha256(MEDIA).hexdigest()
    assert first.media_sha256 == second.media_sha256 == digest
    first_frames, second_frames = frames_of(db, first), frames_of(db, second)
    assert len(first_frames) == len(second_frames) == len(SLIDES)
    assert not {f.image_path for f in first_frames} & {f.image_path for f in second_frames}

    assert client.delete(f"/documents/{first.id}").status_code == 204
    assert all(Path(frame.image_path).is_file() for frame in second_frames)
    assert len(frames_of(db, second)) == len(SLIDES)
    assert_inventory_matches(db, course)


def test_a_job_is_never_given_to_two_workers(
    client: TestClient, db: Session, db_engine, course: Course, transcriber
) -> None:
    document_id = vm.upload(client, course)
    db.commit()
    # Kilit beklenirse test askıda kalmasın, hata versin (SKIP LOCKED bozulursa böyle olur).
    engine = create_engine(db_engine.url, connect_args={"options": "-c lock_timeout=5000"})
    factory = session_factory(engine)
    with factory() as holder, factory() as first, factory() as second:
        # Bir çalıştırıcı işi almak üzere satırı kilitledi: öteki onu atlar, iş yok sanır.
        holder.scalars(
            select(ProcessingJob).where(ProcessingJob.document_id == document_id).with_for_update()
        ).one()
        assert claim_next(first) is None
        holder.rollback()

        claimed = claim_next(first)
        assert claimed is not None and claimed.document_id == document_id
        # Alınan iş `running`: ikinci çalıştırıcı aynı işi yeniden almaz.
        assert claim_next(second) is None
    engine.dispose()
    assert [job.attempts for job in vm.jobs_of(db, document_id)] == [1]


def test_running_the_worker_again_duplicates_nothing(
    client: TestClient, db: Session, course: Course, sessions, transcriber, frames_on
) -> None:
    document = processed(client, db, course, sessions, transcriber)
    frames = frames_of(db, document)
    jobs = [(job.id, job.kind, job.status) for job in vm.jobs_of(db, document.id)]
    assert [kind for _, kind, _ in jobs] == ["transcription", "frames"]
    assert {status for _, _, status in jobs} == {"succeeded"}

    assert vm.run_all(db, sessions, transcriber) == 0

    assert [frame.id for frame in frames_of(db, document)] == [frame.id for frame in frames]
    assert [(j.id, j.kind, j.status) for j in vm.jobs_of(db, document.id)] == jobs
    assert len(transcriber.calls) == 1
    assert_inventory_matches(db, course)
