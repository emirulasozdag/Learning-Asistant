"""#19: video kaynağının doküman karşılıkları ve zaman önceliği karşılaştırması (gerçek DB)."""

import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.embeddings.fake import FakeEmbedder
from tests.conftest import BACKEND_DIR, enroll, make_pdf, make_user
from tests.test_video import LESSON, QUESTION, add_video

sys.path.insert(0, str(BACKEND_DIR.parent / "evaluation"))

from harness.corpus import Locator  # noqa: E402
from harness.fingerprint import file_sha256  # noqa: E402
from harness.run import playback_documents  # noqa: E402
from harness.schemas import GoldItem, Playback, Review, SourceLocator  # noqa: E402
from harness.time_prior import NO_PRIOR, Relation, compare_variants  # noqa: E402

REVIEW = Review(reviewer="instructor-1", reviewed_at=datetime(2026, 11, 2, tzinfo=UTC))
# Videodaki bir cue ile aynı metni taşıyan slayt sayfası ve alakasız bir sayfa.
SLIDES = [
    ("Ikili arama", "hedef kucukse sag yari elenir"),
    ("Yigin", "yigin son giren ilk cikar ve kuyruk ilk giren ilk cikar ama baska bir konu"),
]


def chunk_at(db: Session, document: Document, t_start: float) -> Chunk:
    return db.scalars(
        select(Chunk).where(Chunk.document_id == document.id, Chunk.t_start == t_start)
    ).one()


def test_video_source_lists_matching_document_pages(
    client: TestClient, client_for, db: Session, course: Course, tmp_path: Path
) -> None:
    video = add_video(db, course)
    pdf = make_pdf(tmp_path / "slaytlar.pdf", SLIDES)
    with pdf.open("rb") as file:
        slides_id = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "slides", "declaration": "true"},
            files={"file": (pdf.name, file)},
        ).json()["id"]
    student = make_user(db, "ogrenci@example.com")
    enroll(db, student, course, "student")
    cue = chunk_at(db, video, 200)

    detail = client_for(student).get(f"/sources/{cue.id}").json()

    assert (detail["t_start"], detail["t_end"]) == (cue.t_start, cue.t_end)
    alternatives = detail["alternatives"]
    assert alternatives and alternatives[0]["document_id"] == slides_id
    assert alternatives[0]["page"] == 1 and alternatives[0]["material_type"] == "slides"
    assert alternatives == sorted(alternatives, key=lambda a: -a["similarity"])
    assert all(a["similarity"] >= 0.78 for a in alternatives)
    # Doküman parçasının kendisinde karşılık listesi yok.
    page = db.scalars(select(Chunk).where(Chunk.document_id == slides_id)).first()
    assert client_for(student).get(f"/sources/{page.id}").json()["alternatives"] == []


def test_alternatives_skip_unapproved_unready_and_other_course_documents(
    client: TestClient, db: Session, course: Course, user, tmp_path: Path
) -> None:
    video = add_video(db, course)
    pdf = make_pdf(tmp_path / "slaytlar.pdf", SLIDES)
    with pdf.open("rb") as file:
        slides_id = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "slides", "declaration": "true"},
            files={"file": (pdf.name, file)},
        ).json()["id"]
    other = Course(code="BLM3000", name="Baska", language="tr")
    db.add(other)
    db.commit()
    enroll(db, user, other, "instructor")
    with pdf.open("rb") as file:
        client.post(
            f"/courses/{other.id}/materials",
            data={"material_type": "slides", "declaration": "true"},
            files={"file": ("kopya.pdf", file)},
        )
    cue = chunk_at(db, video, 200)
    assert client.get(f"/sources/{cue.id}").json()["alternatives"]

    for change in ({"approved_at": None}, {"status": "processing"}):
        document = db.get(Document, slides_id)
        for field, value in change.items():
            setattr(document, field, value)
        db.commit()
        assert client.get(f"/sources/{cue.id}").json()["alternatives"] == []
        document.approved_at, document.status = datetime.now(UTC), "ready"
        db.commit()


def test_time_prior_is_compared_per_lecture_on_the_same_questions(
    db: Session, course: Course, tmp_path: Path
) -> None:
    lecture_a = add_video(db, course, name="ders1.vtt")
    lecture_b = add_video(
        db, course, cues=[(t, e, f"{x} ikinci") for t, e, x in LESSON], name="ders2.vtt"
    )
    locator = Locator(db, Path("."))
    videos = playback_documents(db, course, locator)
    sha_a, sha_b = (file_sha256(Path(d.file_path)) for d in (lecture_a, lecture_b))
    items = [
        GoldItem(
            id=f"q-{name}",
            split="calibration",
            kind="answerable",
            question=QUESTION,
            reference_answer="...",
            evidence=[SourceLocator(document_sha256=sha, t_start=700, t_end=705)],
            origin="instructor",
            review=REVIEW,
            playback=Playback(document_sha256=sha, time_s=705),
        )
        for name, sha in (("a", sha_a), ("b", sha_b))
    ]

    results = compare_variants(db, course, items, videos, locator.locate, FakeEmbedder())

    baseline, *with_prior = results
    assert baseline.name == NO_PRIOR and baseline.improved == baseline.worsened == 0
    assert set(baseline.by_lecture) == {sha_a, sha_b}
    production = next(r for r in with_prior if "(üretim)" in r.name)
    for item in items:
        before, after = baseline.per_item_rank[item.id], production.per_item_rank[item.id]
        assert after is not None and (before is None or after <= before)
    assert production.by_relation[Relation.NEAR.value] == 1.0
    assert all(r.improved + r.worsened + r.unchanged == len(items) for r in with_prior)
