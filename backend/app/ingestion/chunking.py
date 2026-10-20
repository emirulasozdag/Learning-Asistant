import math
import re

from app.ingestion.types import ChunkDraft, RawSegment

# multilingual-e5 512 token sınırının altında kalmak için (sunum [D2]).
MAX_CHUNK_TOKENS = 480
# Komşu parçalar arasında bağlam kopmasın diye tekrar edilen yaklaşık token miktarı.
OVERLAP_TOKENS = 60
# Altyazı parçasının en uzun süresi (saniye): bir parça yaklaşık bir dakikalık konuşmadır.
MAX_CHUNK_SECONDS = 60.0
# Türkçe eklemeli bir dil; e5 tokenizer'ı kelime başına ortalama ~1,5 token üretir.
TOKENS_PER_WORD = 1.5

_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text.split()) * TOKENS_PER_WORD)


def chunk_segments(
    segments: list[RawSegment],
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Segmentleri parçalara böler; bir parça asla iki sayfaya taşmaz.

    Kısa bir sayfa tek parça olur. Uzun sayfa önce paragraflara, gerekirse cümlelere,
    en son kelimelere bölünür; birimler `max_tokens` dolana kadar birleştirilir ve
    ardışık parçalar arasında `overlap_tokens` kadar örtüşme bırakılır.
    """
    chunks: list[ChunkDraft] = []
    for segment in segments:
        for text in _split_text(segment.text, max_tokens, overlap_tokens):
            chunks.append(
                ChunkDraft(
                    text=text, page=segment.page, t_start=segment.t_start, t_end=segment.t_end
                )
            )
    return chunks


def _split_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if estimate_tokens(text) <= max_tokens:
        return [text]

    units = [
        unit for paragraph in _PARAGRAPH_BREAK.split(text) for unit in _units(paragraph, max_tokens)
    ]

    chunks: list[str] = []
    current: list[str] = []
    for unit in units:
        if current and estimate_tokens(" ".join([*current, unit])) > max_tokens:
            chunks.append("\n".join(current))
            current = _overlap_tail(current, overlap_tokens, max_tokens - estimate_tokens(unit))
        current.append(unit)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _units(paragraph: str, max_tokens: int) -> list[str]:
    """Paragrafı sığacak birimlere böler: paragraf → cümleler → kelime grupları."""
    paragraph = paragraph.strip()
    if not paragraph:
        return []
    if estimate_tokens(paragraph) <= max_tokens:
        return [paragraph]

    units: list[str] = []
    for sentence in _SENTENCE_END.split(paragraph):
        if estimate_tokens(sentence) <= max_tokens:
            units.append(sentence)
            continue
        words = sentence.split()
        step = max(1, int(max_tokens / TOKENS_PER_WORD))
        units.extend(" ".join(words[i : i + step]) for i in range(0, len(words), step))
    return units


def _overlap_tail(units: list[str], overlap_tokens: int, room: int) -> list[str]:
    """Önceki parçanın sonundaki birimlerden, yeni parçaya sığan kadarını taşır."""
    budget = min(overlap_tokens, room)
    tail: list[str] = []
    for unit in reversed(units):
        if estimate_tokens(" ".join([unit, *tail])) > budget:
            break
        tail.insert(0, unit)
    return tail


def chunk_timed_segments(
    segments: list[RawSegment],
    max_tokens: int = MAX_CHUNK_TOKENS,
    max_seconds: float = MAX_CHUNK_SECONDS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Zamanlı segmentleri (altyazı cue'ları) parçalara birleştirir.

    Ardışık cue'lar token ya da süre tavanı dolana kadar tek parçada toplanır. Bir cue asla
    bölünmez: tavanı tek başına aşan cue kendi başına bir parça olur. Parçanın `t_start`ı ilk
    cue'nun başı, `t_end`i son cue'nun sonudur. Örtüşme cue birimiyledir: önceki parçanın son
    cue'larından, `overlap_tokens` ve tavanlara sığanlar yeni parçanın başına taşınır.
    """
    chunks: list[ChunkDraft] = []
    current: list[RawSegment] = []
    fresh = 0  # `current` içinde henüz bir parçada yer almamış cue sayısı
    for cue in segments:
        if current and not _fits(current, cue, max_tokens, max_seconds):
            chunks.append(_timed_draft(current))
            current = _timed_overlap(current, cue, max_tokens, max_seconds, overlap_tokens)
            fresh = 0
        current.append(cue)
        fresh += 1
    if fresh:
        chunks.append(_timed_draft(current))
    return chunks


def _fits(current: list[RawSegment], cue: RawSegment, max_tokens: int, max_seconds: float) -> bool:
    return (
        estimate_tokens(_joined([*current, cue])) <= max_tokens
        and _span([*current, cue]) <= max_seconds
    )


def _timed_overlap(
    previous: list[RawSegment],
    cue: RawSegment,
    max_tokens: int,
    max_seconds: float,
    overlap_tokens: int,
) -> list[RawSegment]:
    tail: list[RawSegment] = []
    for candidate in reversed(previous):
        extended = [candidate, *tail]
        if estimate_tokens(_joined(extended)) > overlap_tokens or not _fits(
            extended, cue, max_tokens, max_seconds
        ):
            break
        tail = extended
    return tail


def _timed_draft(cues: list[RawSegment]) -> ChunkDraft:
    return ChunkDraft(text=_joined(cues), t_start=cues[0].t_start, t_end=cues[-1].t_end)


def _joined(cues: list[RawSegment]) -> str:
    return " ".join(cue.text for cue in cues)


def _span(cues: list[RawSegment]) -> float:
    return (cues[-1].t_end or 0.0) - (cues[0].t_start or 0.0)
