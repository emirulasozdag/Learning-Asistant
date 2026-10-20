"""Video: VTT yükleme akışı ve oynatma konumu önceliği (gerçek veritabanı, sahte embedder)."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document
from app.embeddings.fake import FakeEmbedder
from app.ingestion.pipeline import ingest_document
from app.retrieval.hybrid import RetrievalParams, retrieve
from app.retrieval.types import VideoPosition
from app.retrieval.video_time import video_neighbors
from app.schemas.materials import MaterialType
from tests.conftest import make_vtt, vtt_text

# Her cue 5 sn sürer ve 100 sn arayla gelir: her cue kendi parçası olur (parça tavanı 60 sn).
LESSON = [
    (0, 5, "ikili arama sirali dizide hedef degeri arar"),
    (100, 105, "ortadaki eleman hedefle karsilastirilir"),
    (200, 205, "hedef kucukse sag yari elenir"),
    (300, 305, "zaman karmasikligi log n olur"),
    (400, 405, "dogrusal arama n zaman alir"),
    (500, 505, "yigin son giren ilk cikar"),
    (600, 605, "kuyruk ilk giren ilk cikar"),
    (700, 705, "zaman"),
]
QUESTION = "ikili arama dizi hedef zaman"


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    return tmp_path / "uploads"


def upload_vtt(client: TestClient, course_id: int, path: Path, **data: str):
    with path.open("rb") as file:
        return client.post(
            f"/courses/{course_id}/materials",
            data={"material_type": "video", **data},
            files={"file": (path.name, file)},
        )


def add_video(
    db: Session, course: Course, cues=LESSON, name: str = "ders.vtt", media_url: str | None = None
) -> Document:
    document, _ = ingest_document(
        db,
        course,
        name,
        vtt_text(cues).encode(),
        MaterialType.VIDEO,
        embedder=FakeEmbedder(),
        media_url=media_url,
    )
    return document


def chunk_at(db: Session, document: Document, t_start: float) -> Chunk:
    return db.scalars(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.t_start == t_start)
    ).one()


def order(result) -> list[str]:
    return [p.source_id for p in result.passages]


# --- yükleme akışı -------------------------------------------------------------------------


def test_vtt_upload_becomes_a_video_document_with_time_chunks(
    client: TestClient, db: Session, course: Course, tmp_path: Path
) -> None:
    path = make_vtt(tmp_path / "ders1.vtt", LESSON)

    response = upload_vtt(client, course.id, path)

    assert response.status_code == 201
    document = response.json()
    assert document["material_type"] == "video"
    assert document["page_count"] == 0 and document["chunk_count"] == len(LESSON)
    assert document["duration_s"] == 705 and document["media_url"] is None
    report = document["report"]
    assert (report["pages_read"], report["empty_pages"]) == (0, 0)
    assert (report["repeated_lines_removed"], report["page_numbers_removed"]) == (0, 0)
    assert (report["duration_s"], report["cues_read"], report["cues_skipped"]) == (705, 8, 0)
    assert report["warnings"] == []
    chunks = db.scalars(select(Chunk).order_by(Chunk.ordinal)).all()
    assert [(c.page, c.t_start, c.t_end) for c in chunks] == [(None, s, e) for s, e, _ in LESSON]
    listed = client.get(f"/courses/{course.id}/materials").json()[0]
    assert listed["duration_s"] == 705 and listed["page_count"] == 0


def test_vtt_is_always_video_even_if_another_type_is_chosen(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    path = make_vtt(tmp_path / "ders1.vtt", LESSON)
    with path.open("rb") as file:
        response = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "notes"},
            files={"file": (path.name, file)},
        )

    assert response.status_code == 201
    assert response.json()["material_type"] == "video"


def test_skipped_cues_are_reported_with_a_warning(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    path = tmp_path / "kismen.vtt"
    path.write_text(vtt_text(LESSON) + "\nbozuk --> 00:00:09.000\nkotu\n", encoding="utf-8")

    report = upload_vtt(client, course.id, path).json()["report"]

    assert (report["cues_read"], report["cues_skipped"]) == (8, 1)
    assert len(report["warnings"]) == 1 and "1" in report["warnings"][0]


@pytest.mark.parametrize(
    "content",
    [b"", b"merhaba dunya", b"WEBVTT\n\n", b"WEBVTT\n\nx --> y\nbozuk\n", b"WEBVTT\n\n\xff\xfe\n"],
)
def test_broken_subtitles_are_rejected_and_leave_nothing_behind(
    client: TestClient, db: Session, course: Course, tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "bozuk.vtt"
    path.write_bytes(content)

    response = upload_vtt(client, course.id, path)

    assert response.status_code == 422 and response.json()["detail"]
    assert db.scalars(select(Document)).all() == []
    assert not list((settings.upload_dir / str(course.id)).glob("*"))


def test_video_type_with_a_non_vtt_file_is_rejected(
    client: TestClient, course: Course, sample_pdf: Path, tmp_path: Path
) -> None:
    video = tmp_path / "ders.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    for path in (sample_pdf, video):
        response = upload_vtt(client, course.id, path)
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "Video dosyası henüz yüklenemiyor; altyazı (.vtt) yükleyin."
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://video.example.com/ders1",
        "javascript:alert(1)",
        "https://",
        "https:///yol",
        "https://:443/yol",
        "ftp://video.example.com/a",
        "//video.example.com/a",
        "https://video.example.com/a b",
        "https://video.example.com/" + "a" * 1000,
    ],
)
def test_media_url_must_be_https_with_a_host(
    client: TestClient, db: Session, course: Course, tmp_path: Path, url: str
) -> None:
    path = make_vtt(tmp_path / "ders1.vtt", LESSON)

    response = upload_vtt(client, course.id, path, media_url=url)

    assert response.status_code == 422
    assert db.scalars(select(Document)).all() == []


def test_media_url_is_only_meaningful_for_video_uploads(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    with sample_pdf.open("rb") as file:
        response = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "notes", "media_url": "https://video.example.com/ders1"},
            files={"file": (sample_pdf.name, file)},
        )

    assert response.status_code == 422


def test_https_media_url_is_stored_and_opaque(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    url = "https://video.example.com/watch?v=abc#kendi-parametresi"
    path = make_vtt(tmp_path / "ders1.vtt", LESSON)

    document = upload_vtt(client, course.id, path, media_url=url).json()

    assert document["media_url"] == url
    assert client.get(f"/courses/{course.id}/materials").json()[0]["media_url"] == url


def test_citation_and_source_detail_carry_the_time_range(
    client: TestClient, course: Course, tmp_path: Path
) -> None:
    url = "https://video.example.com/ders1"
    upload_vtt(client, course.id, make_vtt(tmp_path / "ders1.vtt", LESSON), media_url=url)

    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "hedef kucukse hangi yari elenir?"}
    ).json()

    citation = answer["citations"][0]
    assert (citation["page"], citation["t_start"], citation["t_end"]) == (None, 200, 205)
    hit = next(h for h in answer["retrieval"] if h["source_id"] == citation["source_id"])
    assert (hit["page"], hit["t_start"], hit["t_end"]) == (None, 200, 205)
    source = client.get(f"/sources/{citation['source_id']}").json()
    assert source["material_type"] == "video"
    assert (source["page"], source["t_start"], source["t_end"]) == (None, 200, 205)
    assert source["media_url"] == url
    assert source["page_image_url"] is None and source["highlights"] == []


def test_source_detail_without_media_url_has_none(
    client: TestClient, db: Session, course: Course, upload_dir: Path
) -> None:
    document = add_video(db, course)

    source = client.get(f"/sources/{chunk_at(db, document, 200).id}").json()

    assert source["media_url"] is None and source["t_start"] == 200


def test_pdf_source_keeps_its_file_link(
    client: TestClient, course: Course, sample_pdf: Path
) -> None:
    from tests.test_flow import upload

    document = upload(client, course.id, sample_pdf).json()
    answer = client.post(
        "/ask", json={"course_id": course.id, "question": "Neden sag yari elenir?"}
    ).json()

    source = client.get(f"/sources/{answer['citations'][0]['source_id']}").json()

    assert source["media_url"] == f"/api/documents/{document['id']}/file#page={source['page']}"
    assert source["t_start"] is None and source["page_image_url"]


# --- yakın parçalar ------------------------------------------------------------------------


def test_video_neighbors_window_bounds_are_overlap_inclusive(
    db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)

    def starts(time_s: float, window_s: float = 120, limit: int = 10) -> list[float | None]:
        found = video_neighbors(db, course, VideoPosition(video.id, time_s), window_s, limit)
        return [p.t_start for p in found]

    # Pencere [380, 620]: 400, 500, 600 kesin içeride; 300-305 (sonu 305 < 380) dışarıda.
    assert starts(500) == [500, 400, 600] or starts(500) == [500, 600, 400]
    # Aralığın sonu pencerenin başına tam değerse örtüşür (305 >= 305).
    assert 300 in starts(425, window_s=120)
    assert 300 not in starts(425.5, window_s=120)
    # Başlangıç pencerenin sonuna tam değerse örtüşür.
    assert 600 in starts(480, window_s=120) and 600 not in starts(479.9, window_s=120)
    assert starts(500, window_s=0) == [500]
    assert starts(100000) == []
    assert starts(500, limit=1) == [500]


def test_video_neighbors_are_sorted_by_midpoint_distance(
    db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)

    found = video_neighbors(db, course, VideoPosition(video.id, 440), 200, 10)

    assert [p.t_start for p in found] == [400, 500, 300, 600]


def test_video_neighbors_never_mix_videos_or_courses(
    db: Session, course: Course, upload_dir: Path
) -> None:
    first = add_video(db, course, name="a.vtt")
    second = add_video(db, course, name="b.vtt")
    other = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other)
    db.commit()
    foreign = add_video(db, other, name="c.vtt")

    found = video_neighbors(db, course, VideoPosition(first.id, 100), 120, 10)
    cross_course = video_neighbors(db, course, VideoPosition(foreign.id, 100), 120, 10)

    assert {p.document_id for p in found} == {first.id}
    assert second.id not in {p.document_id for p in found}
    assert cross_course == []


# --- öncelik -------------------------------------------------------------------------------


def test_chunk_in_the_window_rises_compared_to_no_video(
    db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)
    target = str(chunk_at(db, video, 700).id)
    embedder = FakeEmbedder()

    plain = order(retrieve(db, course, QUESTION, k=10, embedder=embedder))
    with_video = order(
        retrieve(db, course, QUESTION, VideoPosition(video.id, 705), k=10, embedder=embedder)
    )

    assert plain.index(target) > 0
    assert with_video.index(target) < plain.index(target)
    assert sorted(with_video) == sorted(plain)  # hiçbir parça elenmedi, eklenmedi


def test_evidence_outside_the_window_is_still_retrieved(
    db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)
    far = str(chunk_at(db, video, 0).id)

    result = retrieve(
        db,
        course,
        "ikili arama sirali dizide hedef degeri arar",
        VideoPosition(video.id, 705),
        k=3,
        embedder=FakeEmbedder(),
    )

    assert order(result)[0] == far and result.relevant


def test_another_videos_same_second_is_not_boosted(
    db: Session, course: Course, upload_dir: Path
) -> None:
    first = add_video(db, course, name="a.vtt")
    second = add_video(db, course, name="b.vtt")
    embedder = FakeEmbedder()
    first_target, second_target = (str(chunk_at(db, v, 700).id) for v in (first, second))

    def position(video: Document, **kwargs) -> list[str]:
        result = retrieve(
            db, course, QUESTION, VideoPosition(video.id, 705), k=20, embedder=embedder, **kwargs
        )
        return order(result)

    for watched, mine, theirs in (
        (first, first_target, second_target),
        (second, second_target, first_target),
    ):
        ranked = position(watched)
        assert ranked.index(mine) < ranked.index(theirs)


def test_zero_video_weight_equals_no_video(db: Session, course: Course, upload_dir: Path) -> None:
    video = add_video(db, course)
    embedder = FakeEmbedder()

    plain = retrieve(db, course, QUESTION, k=10, embedder=embedder)
    off = retrieve(
        db,
        course,
        QUESTION,
        VideoPosition(video.id, 705),
        k=10,
        embedder=embedder,
        params=RetrievalParams(video_weight=0),
    )

    assert order(off) == order(plain)
    assert [p.score for p in off.passages] == [p.score for p in plain.passages]


def test_relevance_gate_is_not_affected_by_the_video(
    db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)
    embedder = FakeEmbedder()

    for question in (QUESTION, "kuantum dolanikilik fotosentez organel"):
        plain = retrieve(db, course, question, embedder=embedder)
        near = retrieve(db, course, question, VideoPosition(video.id, 700), embedder=embedder)
        assert (near.relevant, near.best_similarity, near.keyword_coverage) == (
            plain.relevant,
            plain.best_similarity,
            plain.keyword_coverage,
        )
        assert near.admitted_by_context == plain.admitted_by_context


def test_time_beyond_the_duration_is_clamped_not_an_error(
    client: TestClient, db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)
    body = {"course_id": course.id, "question": QUESTION}

    far = client.post("/ask", json={**body, "video": {"document_id": video.id, "time_s": 1e6}})
    at_end = client.post("/ask", json={**body, "video": {"document_id": video.id, "time_s": 705}})
    plain = client.post("/ask", json=body)

    assert far.status_code == 200
    assert [h["source_id"] for h in far.json()["retrieval"]] == [
        h["source_id"] for h in at_end.json()["retrieval"]
    ]
    assert far.json()["retrieval"] != plain.json()["retrieval"]


def test_stream_accepts_a_valid_video(
    client: TestClient, db: Session, course: Course, upload_dir: Path
) -> None:
    video = add_video(db, course)

    response = client.post(
        "/ask/stream",
        json={
            "course_id": course.id,
            "question": QUESTION,
            "video": {"document_id": video.id, "time_s": 700},
        },
    )

    assert response.status_code == 200 and "event: done" in response.text


# --- invalid_video -------------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/ask", "/ask/stream"])
def test_invalid_video_is_rejected_in_turkish(
    client: TestClient,
    db: Session,
    course: Course,
    sample_pdf: Path,
    upload_dir: Path,
    path: str,
) -> None:
    from tests.test_flow import upload

    other = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other)
    db.commit()
    foreign = add_video(db, other)
    pdf = upload(client, course.id, sample_pdf).json()

    for document_id in (foreign.id, pdf["id"], 99999):
        response = client.post(
            path,
            json={
                "course_id": course.id,
                "question": QUESTION,
                "video": {"document_id": document_id, "time_s": 10},
            },
        )
        assert response.status_code == 422, document_id
        assert "video" in response.json()["detail"].lower()
