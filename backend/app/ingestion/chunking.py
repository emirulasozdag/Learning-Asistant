from app.ingestion.types import ChunkDraft, RawSegment

# multilingual-e5 512 token sınırının altında kalmak için (sunum [D2]).
MAX_CHUNK_TOKENS = 480


def chunk_segments(
    segments: list[RawSegment], max_tokens: int = MAX_CHUNK_TOKENS
) -> list[ChunkDraft]:
    """Segmentleri sayfa / zaman metadata'sını koruyarak parçalara böl."""
    raise NotImplementedError
