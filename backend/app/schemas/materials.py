from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class MaterialType(StrEnum):
    """Onaylı ders materyali türleri (Project 08 tanımı)."""

    TEXTBOOK = "textbook"
    NOTES = "notes"
    SLIDES = "slides"
    PAST_EXAM = "past_exam"
    # OCW "Assignments" ve "Practice Problems": ödev / problem seti ve çözümlü pratik problemler.
    ASSIGNMENT = "assignment"
    PRACTICE_PROBLEM = "practice_problem"
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
    # processing: transkripsiyon sürüyor (parça yok); failed: `error` nedeni söyler. Öğrenciler
    # yalnızca ready dokümanları görür.
    status: Literal["processing", "ready", "failed"] = "ready"
    error: str | None = None
    # Video: "vtt" (yüklenen altyazı) | "asr" (yerel transkripsiyon) ve asr için model kimliği.
    transcript_source: Literal["vtt", "asr"] | None = None
    transcript_model: str | None = None
    # Yalnızca yükleme cevabında dolu.
    report: IngestionReport | None = None


class ChunkPreview(BaseModel):
    """Eğitmenin 'sistem şu parçaları çıkardı' önizlemesi."""

    id: int
    ordinal: int
    page: int | None
    text: str
