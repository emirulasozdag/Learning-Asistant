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


class MaterialUploadResponse(BaseModel):
    document_id: int
    chunk_count: int
