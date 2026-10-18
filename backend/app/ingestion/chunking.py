import math
import re

from app.ingestion.types import ChunkDraft, RawSegment

# multilingual-e5 512 token sınırının altında kalmak için (sunum [D2]).
MAX_CHUNK_TOKENS = 480
# Komşu parçalar arasında bağlam kopmasın diye tekrar edilen yaklaşık token miktarı.
OVERLAP_TOKENS = 60
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
