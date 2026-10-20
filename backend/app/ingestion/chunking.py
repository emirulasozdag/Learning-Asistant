import re

from app.embeddings.base import Embedder
from app.ingestion.types import ChunkDraft, RawSegment

OVERLAP_TOKENS = 60
MAX_CHUNK_SECONDS = 60.0


def chunk_segments(
    segments: list[RawSegment],
    embedder: Embedder,
    max_tokens: int | None = None,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Keep page boundaries and source whitespace; measure complete prefixed model inputs."""
    budget = _budget(embedder, max_tokens, overlap_tokens)
    return [
        ChunkDraft(text=text, page=segment.page, t_start=segment.t_start, t_end=segment.t_end)
        for segment in segments
        for text in _split_text(segment.text, embedder, budget, overlap_tokens)
    ]


def _budget(embedder: Embedder, max_tokens: int | None, overlap_tokens: int) -> int:
    budget = embedder.max_passage_tokens if max_tokens is None else max_tokens
    if budget <= embedder.count_passage_tokens("") or budget > embedder.max_passage_tokens:
        raise ValueError("Chunk token budget must fit the model and leave room for source text")
    if overlap_tokens < 0:
        raise ValueError("Overlap must be nonnegative")
    return budget


def _split_text(text: str, embedder: Embedder, budget: int, overlap: int) -> list[str]:
    if not text.strip():
        return []
    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        # Leave room for overlap when a paragraph itself spans several chunks.
        reserve = min(overlap, (budget - embedder.count_passage_tokens("")) // 4)
        line_budget = budget - reserve if embedder.count_passage_tokens(line) > budget else budget
        for unit in _split_line(line, embedder, line_budget):
            if current and embedder.count_passage_tokens(current + unit) > budget:
                chunks.append(current)
                tail = ""
                for previous in reversed(current.splitlines(keepends=True)):
                    candidate = previous + tail
                    if (
                        embedder.count_passage_tokens(candidate) > overlap
                        or embedder.count_passage_tokens(candidate + unit) > budget
                    ):
                        break
                    tail = candidate
                if not tail:
                    for match in reversed(list(re.finditer(r"\S+", current))):
                        candidate = current[match.start() :]
                        if (
                            embedder.count_passage_tokens(candidate) > overlap
                            or embedder.count_passage_tokens(candidate + unit) > budget
                        ):
                            break
                        tail = candidate
                current = tail
            current += unit
    if current:
        chunks.append(current)
    return chunks


def _split_line(line: str, embedder: Embedder, budget: int):
    """Split oversized lines without dropping characters, including unspaced code/URLs.

    Exponential probing bounds tokenizer work to the next chunk, rather than repeatedly
    tokenizing the entire remaining document. Every chosen slice is measured again.
    """
    start = 0
    while start < len(line):
        low, high = 0, 1
        remaining = len(line) - start
        while (
            high < remaining and embedder.count_passage_tokens(line[start : start + high]) <= budget
        ):
            low, high = high, min(high * 2, remaining)
        if embedder.count_passage_tokens(line[start : start + high]) <= budget:
            end = high
        else:
            while high - low > 1:
                middle = (low + high) // 2
                if embedder.count_passage_tokens(line[start : start + middle]) <= budget:
                    low = middle
                else:
                    high = middle
            end = low
        if end == 0:
            raise ValueError("A source character cannot fit the embedding token budget")
        # Prefer a word boundary, preserving the separating whitespace.
        if end < remaining:
            boundary = max(
                (i + 1 for i, char in enumerate(line[start : start + end]) if char.isspace()),
                default=0,
            )
            if boundary and boundary >= end // 2:
                end = boundary
        piece = line[start : start + end]
        if embedder.count_passage_tokens(piece) > budget:
            raise ValueError("Source slice exceeds the embedding token budget")
        yield piece
        start += end


def chunk_timed_segments(
    segments: list[RawSegment],
    embedder: Embedder,
    max_tokens: int | None = None,
    max_seconds: float = MAX_CHUNK_SECONDS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[ChunkDraft]:
    """Split oversized cues without inventing word timings; retain their original interval."""
    budget = _budget(embedder, max_tokens, overlap_tokens)
    if max_seconds <= 0:
        raise ValueError("Chunk duration must be positive")
    chunks = []
    current: list[RawSegment] = []
    for cue in segments:
        if not cue.text.strip():
            continue
        if embedder.count_passage_tokens(cue.text) > budget:
            if current:
                chunks.append(_timed_draft(current))
                current = []
            chunks.extend(
                ChunkDraft(text=text, t_start=cue.t_start, t_end=cue.t_end)
                for text in _split_text(cue.text, embedder, budget, 0)
            )
            continue
        if current and not _fits([*current, cue], embedder, budget, max_seconds):
            chunks.append(_timed_draft(current))
            tail: list[RawSegment] = []
            for previous in reversed(current):
                candidate = [previous, *tail]
                if embedder.count_passage_tokens(_joined(candidate)) > overlap_tokens or not _fits(
                    [*candidate, cue], embedder, budget, max_seconds
                ):
                    break
                tail = candidate
            current = tail
        current.append(cue)
    if current:
        chunks.append(_timed_draft(current))
    return chunks


def _fits(cues: list[RawSegment], embedder: Embedder, budget: int, max_seconds: float) -> bool:
    return (
        embedder.count_passage_tokens(_joined(cues)) <= budget
        and (cues[-1].t_end or 0.0) - (cues[0].t_start or 0.0) <= max_seconds
    )


def _joined(cues: list[RawSegment]) -> str:
    return " ".join(cue.text for cue in cues)


def _timed_draft(cues: list[RawSegment]) -> ChunkDraft:
    return ChunkDraft(text=_joined(cues), t_start=cues[0].t_start, t_end=cues[-1].t_end)
