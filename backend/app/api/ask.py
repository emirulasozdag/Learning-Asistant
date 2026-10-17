from fastapi import APIRouter

from app.api.not_implemented import not_implemented
from app.schemas.ask import AskRequest, AskResponse

router = APIRouter(prefix="/ask", tags=["qa"])


@router.post("", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    """FR-04..10: video-zaman farkında hibrit arama → cite-or-decline cevap."""
    not_implemented("Grounded Q&A")
