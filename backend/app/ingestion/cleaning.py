from app.ingestion.types import RawSegment


def clean_segments(segments: list[RawSegment]) -> list[RawSegment]:
    """Üst/alt bilgi, tekrar eden başlık, boş satır vb. temizliği."""
    raise NotImplementedError
