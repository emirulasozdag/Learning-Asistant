from dataclasses import dataclass


@dataclass
class RetrievedPassage:
    source_id: str
    text: str
    score: float
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
