import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import DbSession, SessionFactory, checked_video, get_course_for
from app.auth.dependencies import AuthUser, CurrentUser, not_found_error, require_consent
from app.db.models import Course, User
from app.llm.gateway import LLMRole, select_client, select_orchestrator
from app.qa.service import ConversationNotFound, get_conversation
from app.schemas.tutor import TutorTurnRequest, TutorTurnResponse
from app.tutor import service
from app.tutor.tools import BlockEvent, DraftEvent, RetrievalHitsEvent, StatusEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tutor", tags=["tutor"])


@router.post("/turn", response_model=TutorTurnResponse)
def turn(request: TutorTurnRequest, user: AuthUser, db: DbSession) -> TutorTurnResponse:
    """AI Tutor turu: mesaj → orkestratör araç seçer → kökeni etiketli arayüz blokları (ADR-7)."""
    course = _course_for_turn(db, user, request)
    request = request.model_copy(update={"video": checked_video(db, course, request.video)})
    try:
        return service.turn(
            db,
            course,
            request,
            select_orchestrator(),
            select_client(),
            user.user,
            checker=select_client(LLMRole.CHECKER),
            reranker=select_client(LLMRole.RERANKER),
        )
    except ConversationNotFound as exc:
        raise not_found_error("conversation_not_found") from exc


@router.post("/turn/stream")
def turn_stream(
    request: TutorTurnRequest, user: AuthUser, db: DbSession, sessions: SessionFactory
) -> StreamingResponse:
    """Aynı tur, Server-Sent Events olarak.

    Olaylar: `status` (çalışan araç), `retrieval` (bir bloğun bulunan parçaları), `delta`
    (bir bloğun doğrulanmamış taslağı), `block` (doğrulanmış blok; aynı indeksteki taslağın
    yerini alır), `done` (TutorTurnResponse), hata olursa `error`.
    """
    course = _course_for_turn(db, user, request)
    request = request.model_copy(update={"video": checked_video(db, course, request.video)})
    if request.conversation_id is not None:
        try:
            get_conversation(db, course, request.conversation_id, user.id)
        except ConversationNotFound as exc:
            raise not_found_error("conversation_not_found") from exc
    course_id, user_id = course.id, user.id

    def events() -> Iterator[str]:
        with sessions() as stream_db:
            stream_course = stream_db.get(Course, course_id)
            try:
                if stream_course is None:
                    raise ConversationNotFound(request.conversation_id)
                for event in service.turn_stream(
                    stream_db,
                    stream_course,
                    request,
                    select_orchestrator(),
                    select_client(),
                    stream_db.get(User, user_id),
                    checker=select_client(LLMRole.CHECKER),
                    reranker=select_client(LLMRole.RERANKER),
                ):
                    yield _event(event)
            except ConversationNotFound:
                yield _sse("error", {"detail": "Sohbet bulunamadı"})
            except Exception:
                logger.exception("Tutor turu başarısız")
                stream_db.rollback()
                yield _sse("error", {"detail": "Cevap üretilirken beklenmeyen bir hata oluştu."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _course_for_turn(db: DbSession, user: CurrentUser, request: TutorTurnRequest) -> Course:
    """Dersin üyesi olmak ve aydınlatma metnini onaylamış olmak gerekir (`/ask` ile aynı)."""
    course = get_course_for(db, user, request.course_id)
    require_consent(user)
    return course


def _event(event: object) -> str:
    if isinstance(event, StatusEvent):
        return _sse("status", {"tool": event.tool, "label": event.label})
    if isinstance(event, RetrievalHitsEvent):
        hits = [hit.model_dump() for hit in event.hits]
        return _sse("retrieval", {"block_index": event.block_index, "hits": hits})
    if isinstance(event, DraftEvent):
        return _sse("delta", {"block_index": event.block_index, "text": event.text})
    if isinstance(event, BlockEvent):
        return _sse("block", {"index": event.index, "block": event.block.model_dump(mode="json")})
    if isinstance(event, service.TurnDoneEvent):
        return _sse("done", event.response.model_dump(mode="json"))
    raise TypeError(f"Bilinmeyen tutor olayı: {event!r}")


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
