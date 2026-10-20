"""Bir AI Tutor turunu yürütür ve sohbete kaydeder (`/tutor/turn`, `/tutor/turn/stream`).

Sohbetler `/ask` ile aynı tablolarda tutulur; asistan mesajının `meta`'sı cevap özetini
(`answer_meta`, eğitmen etkinliği bunu okur), blokları ve turun izini taşır. LLM'e kullanıcı
kimliği gitmez (ADR-5).
"""

from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course, Message, User
from app.embeddings.base import Embedder
from app.llm.base import LLMClient, ToolCallingClient
from app.qa.service import answer_meta, conversation_history, get_conversation
from app.schemas.tutor import (
    ClarificationBlock,
    CourseAnswerBlock,
    GeneralExplanationBlock,
    NoticeBlock,
    PracticeBlock,
    TutorBlock,
    TutorTurnRequest,
    TutorTurnResponse,
)
from app.tutor.orchestrator import run_turn
from app.tutor.tools import TurnContext, TutorEvent


@dataclass
class TurnDoneEvent:
    response: TutorTurnResponse


def turn_stream(
    db: Session,
    course: Course,
    request: TutorTurnRequest,
    orchestrator: ToolCallingClient | None,
    generator: LLMClient | None,
    user: User | None = None,
    embedder: Embedder | None = None,
    checker: LLMClient | None = None,
    reranker: LLMClient | None = None,
) -> Iterator[TutorEvent | TurnDoneEvent]:
    conversation = get_conversation(db, course, request.conversation_id, user.id if user else None)
    ctx = TurnContext(
        db=db,
        course=course,
        message=request.message,
        history=conversation_history(db, conversation),
        generator=generator,
        checker=checker,
        reranker=reranker,
        user=user,
        conversation_id=conversation.id,
        recent_source_ids=_recent_sources(db, conversation.id),
        video=request.video,
        embedder=embedder,
        general_enabled=settings.tutor_general_knowledge,
    )
    trace = yield from run_turn(ctx, orchestrator)
    response = TutorTurnResponse(conversation_id=conversation.id, blocks=ctx.blocks, trace=trace)
    meta = {
        **_summary(ctx),
        "tutor": True,
        "blocks": [block.model_dump(mode="json") for block in ctx.blocks],
        "trace": trace.model_dump(mode="json"),
    }
    db.add_all(
        [
            Message(conversation_id=conversation.id, role="user", content=request.message),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=transcript(ctx.blocks),
                meta=meta,
            ),
        ]
    )
    db.commit()
    yield TurnDoneEvent(response)


def turn(
    db: Session,
    course: Course,
    request: TutorTurnRequest,
    orchestrator: ToolCallingClient | None,
    generator: LLMClient | None,
    user: User | None = None,
    checker: LLMClient | None = None,
    reranker: LLMClient | None = None,
) -> TutorTurnResponse:
    for event in turn_stream(
        db, course, request, orchestrator, generator, user, checker=checker, reranker=reranker
    ):
        if isinstance(event, TurnDoneEvent):
            return event.response
    raise RuntimeError("Tutor turu sonuçsuz bitti")


def _recent_sources(db: Session, conversation_id: int, turns: int = 3) -> list[str]:
    """Sohbetteki en yeni kaynaklı cevabın alıntıladığı parçalar (son birkaç tur içinde)."""
    metas = db.scalars(
        select(Message.meta)
        .where(Message.conversation_id == conversation_id, Message.role == "assistant")
        .order_by(Message.id.desc())
        .limit(turns)
    )
    for meta in metas:
        if meta and meta.get("cited_source_ids"):
            return [str(source) for source in meta["cited_source_ids"]]
    return []


def transcript(blocks: list[TutorBlock]) -> str:
    """Sonraki turların geçmişi ve kayıt için turun öğrenciye görünen metni."""
    lines: list[str] = []
    for block in blocks:
        if isinstance(block, CourseAnswerBlock):
            lines.append(block.response.answer or block.response.decline_reason or "")
        elif isinstance(block, GeneralExplanationBlock):
            lines.append(f"(Genel bilgi, ders materyalinden değil) {block.text}")
        elif isinstance(block, PracticeBlock):
            lines.append(f"(Pratik sorusu) {block.item.prompt}")
        elif isinstance(block, ClarificationBlock):
            lines.append(block.question)
        elif isinstance(block, NoticeBlock):
            lines.append(block.text)
    return "\n\n".join(line for line in lines if line)


def _summary(ctx: TurnContext) -> dict:
    """Eğitmen etkinliği için tek cevap özeti. Kaynaklı cevap yoksa tur soru sayılmaz."""
    responses = ctx.course_responses
    if not responses:
        return {"counted": False}
    answered = next((r for r in responses if r.outcome == "answered"), None)
    summary = answer_meta(answered or responses[0])
    summary["cited_source_ids"] = sorted({c.source_id for r in responses for c in r.citations})
    return summary
