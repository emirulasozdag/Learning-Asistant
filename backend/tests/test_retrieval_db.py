"""Arama: alakasızlık kapısı, kelime araması, embedding kimliği, ders izolasyonu (veritabanı)."""

from pathlib import Path

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course
from app.embeddings.fake import FakeEmbedder
from app.ingestion.pipeline import ingest_document
from app.retrieval.dense import dense_search
from app.retrieval.hybrid import RetrievalParams, retrieve
from app.retrieval.index import inventory, stale_chunk_count
from app.retrieval.lexical import lexical_search
from app.schemas.materials import MaterialType
from app.scripts.reembed import reembed
from tests.conftest import make_pdf

ENGLISH_PAGES = [
    ("Categories", "What is the role of version control? Version control keeps history."),
    ("Centralized", "Centralized: all users connect to a central master repository."),
    ("Distributed", "Distributed version control: each user has the entire repository."),
    ("History", "Version control lets you see the progress of the project over time."),
]


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    return tmp_path / "uploads"


def ingest(db: Session, course: Course, path: Path) -> None:
    ingest_document(db, course, path.name, path.read_bytes(), MaterialType.NOTES)


def test_relevance_gate_needs_keyword_coverage_not_a_single_shared_word(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    ingest(db, course, sample_pdf)
    embedder = FakeEmbedder()

    on_topic = retrieve(db, course, "Neden sag yari elenir?", embedder=embedder)
    # "arama" derste geçiyor, sorunun geri kalanı geçmiyor: eskiden tek kelime yetiyordu.
    off_topic = retrieve(
        db, course, "Kuantum dolanıklık fotosentez arama organeli", embedder=embedder
    )

    assert on_topic.relevant and on_topic.keyword_coverage == 1.0
    assert off_topic.passages  # kelime eşleşmesi var, aday olarak döner
    assert not off_topic.relevant
    assert off_topic.keyword_coverage is not None and off_topic.keyword_coverage < 0.5


def test_stopwords_of_either_language_do_not_match(
    db: Session, course: Course, tmp_path: Path, upload_dir
) -> None:
    # Ders dili 'tr', materyal İngilizce: "what/is/the" Türkçe yapılandırmada silinmez.
    ingest(db, course, make_pdf(tmp_path / "en.pdf", ENGLISH_PAGES))

    assert lexical_search(db, course, "What is the boiling point of water?", 10) == []


def test_rare_keyword_outranks_words_found_everywhere(
    db: Session, course: Course, tmp_path: Path, upload_dir
) -> None:
    ingest(db, course, make_pdf(tmp_path / "en.pdf", ENGLISH_PAGES))

    hits = lexical_search(db, course, "centralized version control", 10)

    # "version control" 3 sayfada geçer, "centralized" yalnızca birinde: nadir kelime kazanır.
    assert [h.page for h in hits][0] == 2
    assert len(hits) == 4


def test_off_topic_follow_up_is_not_admitted_through_previous_question(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    ingest(db, course, sample_pdf)
    embedder = FakeEmbedder()
    previous = "Ikili arama sirali bir dizide hedef degeri arar"
    question = "Fransa'nın başkenti neresi?"

    def ask(follow_up_floor: float):
        params = RetrievalParams(min_keyword_coverage=0.3, follow_up_min_similarity=follow_up_floor)
        return retrieve(db, course, question, embedder=embedder, context=previous, params=params)

    strict, lenient = ask(0.77), ask(0.0)

    assert not strict.relevant and not strict.admitted_by_context
    # Taban kalkınca önceki sorunun eşleşmeleri kapıyı açar: kuralın koruduğu durum budur.
    assert lenient.relevant and lenient.admitted_by_context


def test_dense_search_uses_only_vectors_of_the_active_embedder(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    ingest(db, course, sample_pdf)
    embedder = FakeEmbedder()
    first = db.scalars(select(Chunk).order_by(Chunk.id)).first()
    db.execute(update(Chunk).where(Chunk.id == first.id).values(embedding_model="e5/other/v1"))
    db.commit()

    hits = dense_search(db, course, embedder.embed_query("ikili arama"), 10, embedder.identity)

    assert len(hits) == 2
    assert str(first.id) not in {h.source_id for h in hits}
    assert stale_chunk_count(db, embedder.identity) == 1


def test_reembed_rebuilds_mismatched_vectors_and_restores_fingerprint(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    ingest(db, course, sample_pdf)
    embedder = FakeEmbedder()
    original = inventory(db, course.id)
    db.execute(update(Chunk).values(embedding_model=None))
    db.commit()
    mixed = inventory(db, course.id)

    assert original.by_embedding == {embedder.identity: 3}
    assert mixed.stale(embedder.identity) == 3 and mixed.fingerprint != original.fingerprint
    assert reembed(db, embedder) == 3
    assert reembed(db, embedder) == 0  # uyumlu vektörlere dokunulmaz
    assert inventory(db, course.id).fingerprint == original.fingerprint
    assert reembed(db, embedder, all_chunks=True) == 3


def test_every_retrieval_step_stays_inside_the_course(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    other = Course(code="FIZ101", name="Fizik", language="tr")
    db.add(other)
    db.commit()
    ingest(db, course, sample_pdf)
    ingest(db, other, sample_pdf)  # aynı metin, başka ders
    own_ids = {str(i) for i in db.scalars(select(Chunk.id).where(Chunk.course_id == course.id))}

    result = retrieve(
        db,
        course,
        "Karmasiklik ne?",
        embedder=FakeEmbedder(),
        context="Ikili arama nedir?",
        k=100,
    )

    assert result.passages
    assert {p.source_id for p in result.passages} <= own_ids


@pytest.mark.parametrize(
    "question", [r"it's a:b \ 'quote' & | ! (x)", "what is the of and", "?!", "ve ile da"]
)
def test_odd_or_stopword_only_questions_do_not_break_keyword_search(
    db: Session, course: Course, sample_pdf: Path, upload_dir, question: str
) -> None:
    ingest(db, course, sample_pdf)

    assert lexical_search(db, course, question, 10) == []


def test_empty_course_returns_nothing_and_is_not_relevant(db: Session, course: Course) -> None:
    result = retrieve(db, course, "Ikili arama nedir?", embedder=FakeEmbedder())

    assert result.passages == [] and not result.relevant


def test_vectors_without_identity_are_not_used_by_dense_search(
    db: Session, course: Course, sample_pdf: Path, upload_dir
) -> None:
    ingest(db, course, sample_pdf)
    embedder = FakeEmbedder()
    db.execute(update(Chunk).values(embedding_model=None))  # migration öncesi vektörler
    db.commit()

    assert (
        dense_search(db, course, embedder.embed_query("ikili arama"), 10, embedder.identity) == []
    )
