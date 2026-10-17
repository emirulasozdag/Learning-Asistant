from app.retrieval.types import RetrievedPassage
from app.schemas.ask import AskResponse


def validate_citations(response: AskResponse, passages: list[RetrievedPassage]) -> bool:
    """JSON şeması + kaynak ID kontrolü: bilinmeyen ID içeren cevap reddedilir."""
    raise NotImplementedError
