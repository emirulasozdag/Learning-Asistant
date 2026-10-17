from pathlib import Path

from app.ingestion.types import RawSegment


def parse_vtt(path: Path) -> list[RawSegment]:
    """VTT altyazı / transkript → t_start / t_end zaman damgalı ham metin. webvtt-py."""
    raise NotImplementedError
