from pathlib import Path

from app.ingestion.types import RawSegment


def transcribe_video(path: Path) -> list[RawSegment]:
    """Altyazısı olmayan ders videosu → zaman damgalı transkript (faster-whisper)."""
    raise NotImplementedError
