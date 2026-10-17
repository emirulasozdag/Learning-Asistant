from pathlib import Path

from app.ingestion.types import RawSegment


def parse_pptx(path: Path) -> list[RawSegment]:
    """PPTX slaytlar → slayt numarası `page` olarak tutulan ham metin. python-pptx."""
    raise NotImplementedError
