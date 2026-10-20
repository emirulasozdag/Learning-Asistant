import re
from collections import Counter
from dataclasses import dataclass, replace

from app.ingestion.types import RawSegment

REPEATED_LINE_RATIO = 0.8
MIN_SEGMENTS_FOR_REPEAT_CHECK = 4
MAX_REPEATED_LINE_LENGTH = 80
_PAGE_NUMBER = re.compile(
    r"^(?:(?:sayfa|page|s\.)\s*)?(\d{1,4})(?:\s*(?:/|of)\s*\d{1,4})?$",
    re.IGNORECASE,
)


@dataclass
class CleaningStats:
    repeated_lines_removed: int = 0
    page_numbers_removed: int = 0
    empty_segments_dropped: int = 0


def clean_segments(segments: list[RawSegment]) -> list[RawSegment]:
    return clean_segments_with_stats(segments)[0]


def clean_segments_with_stats(
    segments: list[RawSegment],
) -> tuple[list[RawSegment], CleaningStats]:
    """Remove furniture only with parser-provided margin evidence, never by text alone.

    Indentation, column spacing, blank lines, hyphens and standalone numbers in the body
    are source content. Missing layout evidence means retaining the line.
    """
    stats = CleaningStats()
    counts: Counter = Counter()
    for segment in segments:
        counts.update(
            {
                _margin_key(line, segment.margin_lines[index])
                for index, line in enumerate(segment.text.split("\n"))
                if index in segment.margin_lines
                and 0 < len(line.strip()) <= MAX_REPEATED_LINE_LENGTH
            }
        )
    repeated = {
        key
        for key, count in counts.items()
        if len(segments) >= MIN_SEGMENTS_FOR_REPEAT_CHECK
        and count >= len(segments) * REPEATED_LINE_RATIO
    }
    cleaned = []
    for segment in segments:
        lines = []
        for index, line in enumerate(segment.text.split("\n")):
            position = segment.margin_lines.get(index)
            number = _PAGE_NUMBER.fullmatch(line.strip()) if position is not None else None
            if number and segment.page == int(number[1]):
                stats.page_numbers_removed += 1
            elif position is not None and _margin_key(line, position) in repeated:
                stats.repeated_lines_removed += 1
            else:
                lines.append(line)
        text = _normalize("\n".join(lines))
        if text.strip():
            cleaned.append(replace(segment, text=text, margin_lines={}))
        else:
            stats.empty_segments_dropped += 1
    return cleaned, stats


def _margin_key(line: str, position: tuple[float, float]) -> tuple[str, int, int]:
    # Require both repeated text and a stable location (5% page bands).
    return line.strip(), round(position[0] * 20), round(position[1] * 20)


def _normalize(text: str) -> str:
    # Keep source spacing and punctuation: normalization must not rewrite code or formulas.
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\v", "\n").replace("\u00a0", " ")


def normalize_timed_segments(
    segments: list[RawSegment],
) -> tuple[list[RawSegment], CleaningStats]:
    stats = CleaningStats()
    cleaned = []
    for segment in segments:
        text = _normalize(segment.text)
        if text.strip():
            cleaned.append(replace(segment, text=text, margin_lines={}))
        else:
            stats.empty_segments_dropped += 1
    return cleaned, stats
