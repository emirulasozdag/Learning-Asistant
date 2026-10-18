from pathlib import Path

import pymupdf

from app.ingestion.types import RawSegment


def parse_pdf(path: Path) -> list[RawSegment]:
    """PDF (ders kitabı, not, geçmiş sınav) → sayfa başına bir segment, sayfa numarası 1'den.

    Boş sayfalar da döner; temizleme adımında atılır. Böylece sayfa sayısı doğru kalır.
    """
    with pymupdf.open(path) as document:
        return [
            RawSegment(text=page.get_text("text", sort=True), page=number)
            for number, page in enumerate(document, start=1)
        ]
