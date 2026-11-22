"""Metin katmanı bozuk PDF'in yüklenmesi: indekse anlamsız metin girmez (veritabanı testi)."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course
from app.ingestion import text_layer
from app.ingestion.ocr import OcrError, OcrResult
from app.ingestion.pipeline import ingest_document
from app.retrieval.lexical import lexical_search
from app.schemas.materials import MaterialType
from tests.test_text_layer import GARBLED, VISIBLE, make_garbled_pdf


@pytest.fixture
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    return tmp_path / "uploads"


@pytest.fixture
def garbled_pdf(tmp_path: Path) -> Path:
    return make_garbled_pdf(tmp_path / "gram-schmidt.pdf", VISIBLE, GARBLED)


def chunks(db: Session, document_id: int) -> list[Chunk]:
    return list(
        db.scalars(select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal))
    )


def ingest(db: Session, course: Course, path: Path):
    return ingest_document(db, course, path.name, path.read_bytes(), MaterialType.NOTES)


def test_garbled_page_is_indexed_with_ocr_text_and_is_searchable(
    db: Session, course: Course, garbled_pdf: Path, upload_dir: Path, monkeypatch
) -> None:
    languages: list[str] = []

    def fake_ocr(png: bytes, langs: str) -> OcrResult:
        languages.append(langs)
        return OcrResult(status="readable", text="\n".join(VISIBLE), confidence=0.95)

    if shutil.which("tesseract") is None:  # CI: gerçek Tesseract yalnızca Docker imajında.
        monkeypatch.setattr(text_layer, "read_png", fake_ocr)

    document, report = ingest(db, course, garbled_pdf)

    stored = chunks(db, document.id)
    assert [chunk.page for chunk in stored] == [1, 2]
    assert "MATLAB" in stored[0].text
    assert "orthonormal" in stored[0].text
    assert not any(token in stored[0].text for token in ("@BA?CD4", "C5,?.Z<", "IJEH[?6"))
    assert document.page_count == 2
    assert any("Sayfa 1" in w and "OCR ile okundu" in w for w in report.warnings)
    assert languages in ([], ["tur+eng"])  # Dersin dili (tr) → Tesseract dil paketleri.

    found = lexical_search(db, course, "orthonormal vectors", k=5)
    assert [passage.source_id for passage in found][:1] == [str(stored[0].id)]


def test_garbled_page_is_not_indexed_when_ocr_is_unavailable(
    db: Session, course: Course, garbled_pdf: Path, upload_dir: Path, monkeypatch
) -> None:
    def no_tesseract(png: bytes, langs: str) -> OcrResult:
        raise OcrError("Tesseract çalıştırılamadı.")

    monkeypatch.setattr(text_layer, "read_png", no_tesseract)

    document, report = ingest(db, course, garbled_pdf)

    stored = chunks(db, document.id)
    assert [chunk.page for chunk in stored] == [2]
    assert "Orthogonal matrices" in stored[0].text
    assert document.page_count == 2
    assert report.empty_pages == 1
    assert any(
        "Sayfa 1" in w and "OCR çalışmadı" in w and "aramaya alınmadı" in w for w in report.warnings
    )
