from pathlib import Path

from app.ingestion.types import RawSegment


def parse_pdf(path: Path) -> list[RawSegment]:
    """PDF (ders kitabı, not, geçmiş sınav) → sayfa numaralı ham metin. PyMuPDF."""
    raise NotImplementedError
