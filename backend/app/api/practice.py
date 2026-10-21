from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, get_course_for
from app.api.errors import ApiError
from app.auth.dependencies import (
    AuthUser,
    not_found_error,
    require_consent,
    require_course_role,
)
from app.db.models import Course
from app.generation.grade import GradingError
from app.llm.gateway import LLMRole, select_client
from app.practice import service
from app.schemas.evaluation import AnswerFeedback, AnswerSubmission
from app.schemas.practice import PracticeItem, PracticeRequest

router = APIRouter(prefix="/practice", tags=["practice"])


@router.post("", response_model=PracticeItem)
def generate_practice(request: PracticeRequest, user: AuthUser, db: DbSession) -> PracticeItem:
    """FR-11..12: kaynak pasajdan pratik sorusu üret, otomatik kontrollerden geçir.

    Kontrolden geçen soru üretilemezse 422 `no_valid_item`; anahtar ve referans cevap dönmez.
    """
    course = get_course_for(db, user, request.course_id)
    require_consent(user)
    follow_up = None
    if request.follow_up_of_attempt_id is not None:
        follow_up = service.own_attempt(db, request.follow_up_of_attempt_id, user.user, course)
        if follow_up is None:
            raise not_found_error("practice_item_not_found")
    try:
        question = service.create_question(
            db,
            course,
            user.user,
            request.type,
            request.difficulty or "medium",
            service.PracticeContext(
                topic=request.topic, source_id=request.source_id, follow_up_of=follow_up
            ),
            select_client(),
            select_client(LLMRole.CHECKER),
            reranker=select_client(LLMRole.RERANKER),
        )
    except service.NoValidItem as exc:
        raise ApiError(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.reason, "no_valid_item") from exc
    return service.to_item(question)


@router.post("/{item_id}/answer", response_model=AnswerFeedback)
def submit_answer(
    item_id: int, submission: AnswerSubmission, user: AuthUser, db: DbSession
) -> AnswerFeedback:
    """FR-13: rubrik + referans cevapla değerlendir, eksikleri açıkla (resmî not değildir).

    Sorunun dersi `item_id`'den çözülür; üye olmayana 404 (varlık sızdırılmaz).
    """
    question = service.released_question(db, item_id)
    if question is None:
        raise not_found_error("practice_item_not_found")
    require_course_role(user, question.course_id, not_found="practice_item_not_found")
    require_consent(user)
    course = db.get(Course, question.course_id)
    assert course is not None
    try:
        _, feedback = service.answer_question(
            db, question, user.user, submission, select_client(), course_name=course.name
        )
    except service.InvalidSubmission as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except GradingError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return feedback
