from dataclasses import dataclass


class IngestionError(ValueError):
    """Kullanıcıya gösterilecek, düzeltilebilir bir yükleme hatası."""


@dataclass
class RawSegment:
    """Parser çıktısı: konumu (sayfa veya zaman aralığı) bilinen ham metin."""

    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None


@dataclass
class ChunkDraft:
    """İndekslenmeye hazır parça; embedding ve tsvector DB katmanında eklenir."""

    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
