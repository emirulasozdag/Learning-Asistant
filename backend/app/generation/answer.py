from app.retrieval.types import RetrievedPassage
from app.schemas.ask import AskRequest, AskResponse


def generate_answer(request: AskRequest, passages: list[RetrievedPassage]) -> AskResponse:
    """Cite-or-decline: kaynak ID'li cevap üret; kanıt yetersizse reddet."""
    raise NotImplementedError
