from dataclasses import dataclass, field


class IngestionError(ValueError):
    """Kullanıcıya gösterilecek, düzeltilebilir bir yükleme hatası."""


@dataclass
class RawSegment:
    """Parser çıktısı: konumu (sayfa veya zaman aralığı) bilinen ham metin."""

    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
    # Text-line index -> normalized (x, y), only with page-margin evidence.
    margin_lines: dict[int, tuple[float, float]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ChunkDraft:
    """İndekslenmeye hazır parça; embedding ve tsvector DB katmanında eklenir."""

    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
