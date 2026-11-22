"""Çoklu ders yalıtımı (#28): iki ders aynı sözcükleri taşır (notlar, video transkripti, slayt
kareleri); A dersinde yapılan hiçbir arama, soru, tutor turu ya da doküman isteği B'nin verisini
döndürmez ya da varlığını sızdırmaz. Gerçek veritabanı; embedder, OCR ve LLM sahtedir.

A: `course` (eğitmeni `user`). B: aynı içerikli ikinci ders, ayrı eğitmen. `student_a` yalnızca
A'nın; `student_ab` iki dersin de öğrencisidir (en güçlü durum: B'ye erişimi olan biri bile A'da
B'nin verisini göremez).
"""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document, ProcessingJob, VideoFrame
from app.embeddings.fake import FakeEmbedder
from app.retrieval.dense import dense_search
from app.retrieval.frames import frame_search
from app.retrieval.hybrid import retrieve
from app.retrieval.lexical import lexical_search
from app.retrieval.types import VideoPosition
from tests import test_frames_db
from tests.conftest import SAMPLE_PAGES, enroll, make_pdf, make_user
from tests.test_answer import FakeLLM
from tests.test_flow import parse_sse, upload
from tests.test_tutor import ANSWER, use
from tests.test_video import LESSON, QUESTION, add_video

# Kare fikstürleri (sahte kare çıkarma + OCR, iş çalıştırıcı) test_frames_db'den.
frames_on = test_frames_db.frames_on
run_jobs = test_frames_db.run_jobs
transcriber = test_frames_db.transcriber

# İki derste de geçen sözcükler: notlarda, transkriptte ve slayt yazısında.
SHARED_QUESTIONS = [
    "Neden sag yari elenir?",
    QUESTION,
    "Dijkstra kaynak kuyruk hedef",
    "burayı anlamadım",
]


def _material(client: TestClient, db: Session, course: Course, pdf: Path) -> SimpleNamespace:
    """Derse not (PDF) ve altyazılı video yükler, videoya kareleri ekler."""
    notes = upload(client, course.id, pdf)
    assert notes.status_code == 201, notes.text
    video = add_video(db, course, LESSON)
    db.commit()
    attached = test_frames_db.attach(client, video)
    assert attached.status_code == 200, attached.text
    return SimpleNamespace(notes=notes.json()["id"], video=video)


def _ids(db: Session, course: Course) -> SimpleNamespace:
    db.expire_all()
    documents = set(db.scalars(select(Document.id).where(Document.course_id == course.id)))
    chunks = set(db.scalars(select(Chunk.id).where(Chunk.course_id == course.id)))
    frames = set(db.scalars(select(VideoFrame.id).where(VideoFrame.course_id == course.id)))
    return SimpleNamespace(
        documents=documents, chunks={str(c) for c in chunks}, frames=frames, raw_chunks=chunks
    )


@pytest.fixture
def world(
    db: Session, client_for, user, course: Course, tmp_path: Path, frames_on, run_jobs
) -> SimpleNamespace:
    instructor_b = make_user(db, "egitmen-b@example.com", can_create_courses=True)
    course_b = Course(code="MAT1806", name="Lineer Cebir", language="tr")
    db.add(course_b)
    db.commit()
    enroll(db, instructor_b, course_b, "instructor")
    student_a = make_user(db, "ogrenci-a@example.com")
    enroll(db, student_a, course, "student")
    student_ab = make_user(db, "ogrenci-ab@example.com")
    enroll(db, student_ab, course, "student")
    enroll(db, student_ab, course_b, "student")

    # Aynı sayfalar, aynı transkript, aynı slayt yazısı: yalnızca ders farklı.
    pdf_a = make_pdf(tmp_path / "notlar-a.pdf", SAMPLE_PAGES, header="BLM2512")
    pdf_b = make_pdf(tmp_path / "notlar-b.pdf", SAMPLE_PAGES, header="MAT1806")
    a = _material(client_for(user), db, course, pdf_a)
    b = _material(client_for(instructor_b), db, course_b, pdf_b)
    assert run_jobs() == 2

    world = SimpleNamespace(
        a=course,
        b=course_b,
        instructor_a=user,
        instructor_b=instructor_b,
        student_a=student_a,
        student_ab=student_ab,
        video_a=a.video,
        video_b=b.video,
        notes_a=a.notes,
        notes_b=b.notes,
        ids_a=_ids(db, course),
        ids_b=_ids(db, course_b),
    )
    # Ön koşul: iki derste de eşit miktarda, okunabilir yazılı kare dahil içerik var.
    assert len(world.ids_a.chunks) == len(world.ids_b.chunks) > 0
    assert len(world.ids_a.frames) == len(world.ids_b.frames) == len(test_frames_db.SLIDES)
    return world


def collect(value: object, key: str) -> set:
    """JSON gövdesindeki (iç içe) `key` alanlarının bütün değerleri."""
    found: set = set()
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key and item is not None and not isinstance(item, dict | list):
                found.add(item)
            found |= collect(item, key)
    elif isinstance(value, list):
        for item in value:
            found |= collect(item, key)
    return found


def assert_only_course_a(world: SimpleNamespace, body: object) -> None:
    """Gövdedeki her kaynak, doküman ve kare A'nın; B'nin hiçbir kimliği geçmez."""
    sources = {str(s) for s in collect(body, "source_id")}
    documents = collect(body, "document_id")
    frames = collect(body, "frame_id")
    assert sources <= world.ids_a.chunks, sources - world.ids_a.chunks
    assert documents <= world.ids_a.documents, documents - world.ids_a.documents
    assert frames <= world.ids_a.frames, frames - world.ids_a.frames
    assert not sources & world.ids_b.chunks
    assert not documents & world.ids_b.documents


def assert_not_found(response, code: str = "document_not_found") -> None:
    assert response.status_code == 404, response.text
    assert response.json()["code"] == code


# --- arama katmanı ---------------------------------------------------------------------------


@pytest.mark.parametrize("question", SHARED_QUESTIONS)
def test_retrieval_in_one_course_never_returns_the_other_courses_passages(
    db: Session, world: SimpleNamespace, question: str
) -> None:
    embedder = FakeEmbedder()
    for course, mine, video in (
        (world.a, world.ids_a, world.video_a),
        (world.b, world.ids_b, world.video_b),
    ):
        plain = retrieve(db, course, question, k=20, embedder=embedder)
        paused = retrieve(
            db, course, question, VideoPosition(video.id, 210), k=20, embedder=embedder
        )
        lexical = lexical_search(db, course, question, 50)
        dense = dense_search(db, course, embedder.embed_query(question), 50, embedder.identity)
        for passages in (plain.passages, paused.passages, lexical, dense):
            assert {p.source_id for p in passages} <= mine.chunks
            assert {p.document_id for p in passages} <= mine.documents
        assert paused.video_moment is not None and paused.video_moment.document_id == video.id
    # Anlamlı karşılaştırma: aynı soru B'de de bir şey bulur (ama yalnızca B'den).
    assert lexical_search(db, world.b, "ikili arama", 50)


def test_paused_moment_of_another_courses_video_is_ignored_by_retrieval(
    db: Session, world: SimpleNamespace
) -> None:
    """API 422 verir (aşağıda); arama katmanı da kendi başına B'nin videosunu kullanmaz."""
    embedder = FakeEmbedder()
    foreign = VideoPosition(world.video_b.id, 210)

    for question in SHARED_QUESTIONS:
        result = retrieve(db, world.a, question, foreign, k=20, embedder=embedder)
        assert result.video_moment is None and result.deictic is False
        assert {p.source_id for p in result.passages} <= world.ids_a.chunks


def test_frame_search_stays_in_the_course_with_its_context(
    db: Session, world: SimpleNamespace
) -> None:
    for course, mine, video in (
        (world.a, world.ids_a, world.video_a),
        (world.b, world.ids_b, world.video_b),
    ):
        hits = frame_search(db, course, "Dijkstra kaynak mid hedef", FakeEmbedder(), k=10)

        assert len(hits) == 3  # okunabilir ve kısmen okunabilir kareler; yalnızca bu dersten
        for hit in hits:
            assert hit.frame.id in mine.frames and hit.frame.document_id == video.id
            assert {chunk.id for chunk in hit.transcript} <= mine.raw_chunks
            assert {frame.id for frame in hit.neighbors} <= mine.frames


# --- soru-cevap (/ask) -----------------------------------------------------------------------


@pytest.mark.parametrize("who", ["student_a", "student_ab"])
@pytest.mark.parametrize("question", SHARED_QUESTIONS)
def test_answers_in_course_a_cite_only_course_a(
    client_for, world: SimpleNamespace, who: str, question: str
) -> None:
    client = client_for(getattr(world, who))
    payload = {"course_id": world.a.id, "question": question}

    plain = client.post("/ask", json=payload)
    paused = client.post(
        "/ask", json={**payload, "video": {"document_id": world.video_a.id, "time_s": 210}}
    )
    stream = client.post("/ask/stream", json=payload)

    for response in (plain, paused, stream):
        assert response.status_code == 200, response.text
    assert_only_course_a(world, plain.json())
    assert_only_course_a(world, paused.json())
    assert paused.json()["video_moment"]["document_id"] == world.video_a.id
    assert_only_course_a(world, [data for _, data in parse_sse(stream.text)])


@pytest.mark.parametrize("path", ["/ask", "/ask/stream", "/tutor/turn", "/tutor/turn/stream"])
def test_paused_video_of_another_course_is_rejected(
    client_for, db: Session, world: SimpleNamespace, path: str
) -> None:
    """B'ye üye olan öğrenci bile A'da soru sorarken B'nin videosunu gösteremez."""
    text = "question" if path.startswith("/ask") else "message"
    payload = {
        "course_id": world.a.id,
        text: "burayı anlamadım",
        "video": {"document_id": world.video_b.id, "time_s": 210},
    }

    response = client_for(world.student_ab).post(path, json=payload)

    assert response.status_code == 422, response.text
    assert_only_course_a(world, response.json())


def test_conversation_of_another_course_cannot_be_continued(
    client_for, world: SimpleNamespace
) -> None:
    client = client_for(world.student_ab)
    in_b = client.post("/ask", json={"course_id": world.b.id, "question": QUESTION}).json()

    response = client.post(
        "/ask",
        json={
            "course_id": world.a.id,
            "question": QUESTION,
            "conversation_id": in_b["conversation_id"],
        },
    )

    assert_not_found(response, "conversation_not_found")


# --- AI Tutor ---------------------------------------------------------------------------------


@pytest.mark.parametrize("video", [False, True])
def test_tutor_turn_in_course_a_cites_only_course_a(
    client_for, world: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, video: bool
) -> None:
    use(monkeypatch, None, FakeLLM([ANSWER]))
    extra = {"video": {"document_id": world.video_a.id, "time_s": 210}} if video else {}
    client = client_for(world.student_ab)

    for message in ("Neden sag yari elenir?", "burayı anlamadım" if video else QUESTION):
        response = client.post(
            "/tutor/turn", json={"course_id": world.a.id, "message": message, **extra}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert collect(body, "source_id"), body  # gerçekten alıntı yaptı
        assert_only_course_a(world, body)

    stream = client.post(
        "/tutor/turn/stream", json={"course_id": world.a.id, "message": QUESTION, **extra}
    )
    assert stream.status_code == 200
    assert_only_course_a(world, [data for _, data in parse_sse(stream.text)])


# --- kaynak görüntüleyici ve doküman uçları ----------------------------------------------------


def test_source_of_course_a_shows_only_course_a_alternatives_and_frames(
    client_for, world: SimpleNamespace
) -> None:
    """Video parçasının "aynı içerik" karşılıkları B'de birebir aynı metinle de var; yalnızca
    A'nınkiler gösterilir. Ekrandaki kareler de A'nın videosundandır."""
    client = client_for(world.student_ab)
    video_chunks = sorted(chunk.id for chunk in world.video_a.chunks)

    for chunk in video_chunks:
        body = client.get(f"/sources/{chunk}").json()
        assert body["course_id"] == world.a.id
        assert_only_course_a(world, body)
        assert {frame["document_id"] for frame in body["frames"]} <= {world.video_a.id}
    details = [client.get(f"/sources/{c}").json() for c in video_chunks]
    # Ön koşul: karşılık ve kare gerçekten gösteriliyor (boş liste yalıtımı kanıtlamaz).
    assert any(d["frames"] for d in details) and any(d["alternatives"] for d in details)


@pytest.mark.parametrize("who", ["student_a", "instructor_a"])
def test_course_b_sources_and_documents_are_404_for_course_a_members(
    client_for, db: Session, world: SimpleNamespace, who: str
) -> None:
    client = client_for(getattr(world, who))
    frame_b = min(world.ids_b.frames)
    frame_a = min(world.ids_a.frames)

    for chunk in world.ids_b.chunks:
        assert_not_found(client.get(f"/sources/{chunk}"), "source_not_found")
    for document in world.ids_b.documents:
        for path in ("chunks", "frames", "file", "pages/1.png", f"frames/{frame_b}.png"):
            assert_not_found(client.get(f"/documents/{document}/{path}"))
    # B'nin karesi A'nın dokümanı üzerinden de istenemez.
    response = client.get(f"/documents/{world.video_a.id}/frames/{frame_b}.png")
    assert response.status_code == 404
    assert client.get(f"/documents/{world.video_a.id}/frames/{frame_a}.png").status_code == 200
    assert_not_found(client.get(f"/courses/{world.b.id}/materials"), "course_not_found")


def test_course_a_instructor_cannot_change_course_b_documents(
    client_for, db: Session, world: SimpleNamespace, tmp_path: Path
) -> None:
    client = client_for(world.instructor_a)
    jobs_before = db.scalars(select(ProcessingJob.id)).all()

    attached = test_frames_db.attach(client, world.video_b)
    deleted = [client.delete(f"/documents/{d}") for d in sorted(world.ids_b.documents)]
    cancelled = client.post(f"/documents/{world.video_b.id}/cancel")
    pdf = make_pdf(tmp_path / "sizinti.pdf", SAMPLE_PAGES)
    uploaded = upload(client, world.b.id, pdf)

    assert_not_found(attached)
    for response in (*deleted, cancelled):
        assert_not_found(response)
    assert_not_found(uploaded, "course_not_found")
    db.expire_all()
    assert db.scalars(select(ProcessingJob.id)).all() == jobs_before
    assert _ids(db, world.b).documents == world.ids_b.documents
    assert _ids(db, world.b).frames == world.ids_b.frames
    # Kendi dersinde aynı işlemler çalışır (yetki A'ya özgü, genel değil).
    assert client.delete(f"/documents/{world.notes_a}").status_code == 204


def test_materials_list_of_course_a_shows_only_course_a(client_for, world: SimpleNamespace) -> None:
    for who in ("student_a", "student_ab", "instructor_a"):
        listed = client_for(getattr(world, who)).get(f"/courses/{world.a.id}/materials").json()
        assert {document["id"] for document in listed} == world.ids_a.documents
