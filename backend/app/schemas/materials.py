from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class MaterialType(StrEnum):
    """Onaylı ders materyali türleri (Project 08 tanımı)."""

    TEXTBOOK = "textbook"
    NOTES = "notes"
    SLIDES = "slides"
    PAST_EXAM = "past_exam"
    TRANSCRIPT = "transcript"
    VIDEO = "video"


class IngestionReport(BaseModel):
    """Yükleme hattının adım adım özeti: eğitmen ekranında gösterilir."""

    pages_read: int
    empty_pages: int
    repeated_lines_removed: int
    page_numbers_removed: int
    chunks: int
    vectors: int
    vector_dim: int
    embedding_model: str
    # Adım süreleri (ms): parse, clean, chunk, embed
    timings_ms: dict[str, int]
    # Video / altyazı yüklemesinde doldurulur (sayfa tabanlı dosyalarda None).
    duration_s: float | None = None
    cues_read: int | None = None
    cues_skipped: int | None = None
    warnings: list[str] = []


class DocumentOut(BaseModel):
    """Yüklenmiş bir ders dokümanı ve ondan çıkarılan parça sayısı."""

    id: int
    course_id: int
    title: str
    material_type: MaterialType
    filename: str
    page_count: int
    chunk_count: int
    created_at: datetime
    file_url: str
    # Yalnızca video dokümanında (material_type = "video").
    duration_s: float | None = None
    media_url: str | None = None
    # Yalnızca yükleme cevabında dolu.
    report: IngestionReport | None = None


class ChunkPreview(BaseModel):
    """Eğitmenin 'sistem şu parçaları çıkardı' önizlemesi."""

    id: int
    ordinal: int
    page: int | None
    text: str
