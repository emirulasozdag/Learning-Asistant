import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, SessionFactory, get_course_or_404
from app.llm.gateway import select_client
from app.qa import service
from app.schemas.ask import AskRequest, AskResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ask", tags=["qa"])


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, db: DbSession) -> AskResponse:
    """Seçili dersin materyalinde ara → kaynaklı cevap ya da 'materyalde yok'."""
    course = get_course_or_404(db, request.course_id)
    try:
        return service.ask(db, course, request, select_client())
    except service.ConversationNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sohbet bulunamadı") from exc


@router.post("/stream")
def ask_stream(request: AskRequest, db: DbSession, sessions: SessionFactory) -> StreamingResponse:
    """Aynı akış, Server-Sent Events olarak.

    Olaylar: `retrieval` (bulunan parçalar), `delta` (doğrulanmamış taslak metin parçası),
    `done` (doğrulanmış AskResponse; taslağın yerini her zaman alır), hata olursa `error`.
    """
    get_course_or_404(db, request.course_id)

    def events() -> Iterator[str]:
        with sessions() as stream_db:
            course = get_course_or_404(stream_db, request.course_id)
            try:
                for event in service.ask_stream(stream_db, course, request, select_client()):
                    if isinstance(event, service.RetrievalEvent):
                        yield _sse("retrieval", [hit.model_dump() for hit in event.hits])
                    elif isinstance(event, service.DeltaEvent):
                        yield _sse("delta", {"text": event.text})
                    else:
                        yield _sse("done", event.response.model_dump())
            except service.ConversationNotFound:
                yield _sse("error", {"detail": "Sohbet bulunamadı"})
            except Exception:
                # Akış başladıktan sonra HTTP hata kodu gönderilemez; hatayı olay olarak bildir.
                logger.exception("Soru-cevap akışı başarısız")
                stream_db.rollback()
                yield _sse("error", {"detail": "Cevap üretilirken beklenmeyen bir hata oluştu."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
