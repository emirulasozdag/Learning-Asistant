import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import DbSession, SessionFactory, checked_video, get_course_for
from app.auth.dependencies import AuthUser, CurrentUser, not_found_error, require_consent
from app.db.models import Course
from app.llm.gateway import select_client
from app.qa import service
from app.schemas.ask import AskRequest, AskResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ask", tags=["qa"])


@router.post("", response_model=AskResponse)
def ask(request: AskRequest, user: AuthUser, db: DbSession) -> AskResponse:
    """Seçili dersin materyalinde ara → kaynaklı cevap ya da 'materyalde yok'.

    Dersin üyeleri sorabilir; soru ve cevap sorana bağlı sohbete kaydedilir (ADR-4).
    """
    course = _course_for_question(db, user, request)
    request = _checked_video(db, course, request)
    try:
        return service.ask(db, course, request, select_client(), user_id=user.id)
    except service.ConversationNotFound as exc:
        raise not_found_error("conversation_not_found") from exc


@router.post("/stream")
def ask_stream(
    request: AskRequest, user: AuthUser, db: DbSession, sessions: SessionFactory
) -> StreamingResponse:
    """Aynı akış, Server-Sent Events olarak.

    Olaylar: `retrieval` (bulunan parçalar), `delta` (doğrulanmamış taslak metin parçası),
    `done` (doğrulanmış AskResponse; taslağın yerini her zaman alır), hata olursa `error`.
    Yetki ve sohbet sahipliği akış başlamadan denetlenir (hata HTTP koduyla döner).
    """
    course = _course_for_question(db, user, request)
    request = _checked_video(db, course, request)
    if request.conversation_id is not None:
        try:
            service.get_conversation(db, course, request.conversation_id, user.id)
        except service.ConversationNotFound as exc:
            raise not_found_error("conversation_not_found") from exc
    course_id, user_id = course.id, user.id

    def events() -> Iterator[str]:
        with sessions() as stream_db:
            stream_course = stream_db.get(Course, course_id)
            try:
                if stream_course is None:
                    raise service.ConversationNotFound(request.conversation_id)
                for event in service.ask_stream(
                    stream_db, stream_course, request, select_client(), user_id=user_id
                ):
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


def _course_for_question(db: DbSession, user: CurrentUser, request: AskRequest) -> Course:
    """Dersin üyesi olmak ve aydınlatma metnini onaylamış olmak gerekir."""
    course = get_course_for(db, user, request.course_id)
    require_consent(user)
    return course


def _checked_video(db: Session, course: Course, request: AskRequest) -> AskRequest:
    return request.model_copy(update={"video": checked_video(db, course, request.video)})


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
