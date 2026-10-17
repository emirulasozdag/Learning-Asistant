from enum import StrEnum


class Condition(StrEnum):
    """150 test sorusunun koşulduğu 4 karşılaştırma koşulu."""

    NO_RAG = "no_rag"
    BASIC_RAG = "basic_rag"
    FULL = "full"
    FULL_VIDEO_TIME = "full_video_time"
