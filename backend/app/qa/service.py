import re
from collections.abc import Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Conversation, Course, Message
from app.embeddings.base import Embedder
from app.generation.answer import stream_answer
from app.llm.base import ChatMessage, LLMClient
from app.retrieval.hybrid import retrieve
from app.retrieval.types import RetrievalResult
from app.schemas.ask import AskRequest, AskResponse, RetrievalHit

# LLM'e verilen önceki soru-cevap sayısı.
HISTORY_TURNS = 3
_CITATION_MARK = re.compile(r"\s?\[\d+\]")


class ConversationNotFound(LookupError):
    pass


@dataclass
class RetrievalEvent:
    hits: list[RetrievalHit]


@dataclass
class DeltaEvent:
    text: str


@dataclass
class DoneEvent:
    response: AskResponse


QAEvent = RetrievalEvent | DeltaEvent | DoneEvent


def get_conversation(db: Session, course: Course, conversation_id: int | None) -> Conversation:
    """Var olan sohbeti getirir ya da yenisini başlatır. Başka dersin sohbeti kullanılamaz."""
    if conversation_id is None:
        conversation = Conversation(course_id=course.id)
        db.add(conversation)
        db.flush()
        return conversation
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.course_id != course.id:
        raise ConversationNotFound(conversation_id)
    return conversation


def ask_stream(
    db: Session,
    course: Course,
    request: AskRequest,
    llm: LLMClient | None,
    embedder: Embedder | None = None,
) -> Iterator[QAEvent]:
    """Önce bulunan parçalar, sonra cevap metni parça parça, en sonda doğrulanmış cevap."""
    conversation = get_conversation(db, course, request.conversation_id)
    history = _history(db, conversation)

    # Takip sorusu ("peki karmaşıklığı ne?") tek başına eksik kalabilir; önceki soru
    # bağlam olarak ayrıca aranır.
    previous_question = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    retrieval = retrieve(
        db,
        course,
        request.question,
        request.video_time_s,
        embedder=embedder,
        context=previous_question,
    )
    yield RetrievalEvent(_hits(retrieval, cited=set()))

    response: AskResponse | None = None
    for item in stream_answer(course, request.question, history, retrieval, llm):
        if isinstance(item, AskResponse):
            response = item
        else:
            yield DeltaEvent(item)
    assert response is not None

    cited = {c.source_id for c in response.citations}
    response.conversation_id = conversation.id
    response.retrieval = _hits(retrieval, cited)
    response.similarity_threshold = settings.retrieval_min_similarity
    response.best_similarity = retrieval.best_similarity

    db.add_all(
        [
            Message(conversation_id=conversation.id, role="user", content=request.question),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=response.answer or response.decline_reason or "",
                meta={
                    "declined": response.declined,
                    "mode": response.mode,
                    "model": response.model,
                    "cited_source_ids": sorted(cited),
                },
            ),
        ]
    )
    db.commit()
    yield DoneEvent(response)


def ask(
    db: Session,
    course: Course,
    request: AskRequest,
    llm: LLMClient | None,
    embedder: Embedder | None = None,
) -> AskResponse:
    for event in ask_stream(db, course, request, llm, embedder):
        if isinstance(event, DoneEvent):
            return event.response
    raise RuntimeError("Soru-cevap akışı sonuçsuz bitti")


def _history(db: Session, conversation: Conversation) -> list[ChatMessage]:
    """Son birkaç soru-cevap; alıntı numaraları atılır (o turun kaynaklarına aittir)."""
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(HISTORY_TURNS * 2)
    ).all()
    return [
        {"role": m.role, "content": _CITATION_MARK.sub("", m.content)}  # type: ignore[typeddict-item]
        for m in reversed(rows)
    ]


def _hits(retrieval: RetrievalResult, cited: set[str]) -> list[RetrievalHit]:
    return [
        RetrievalHit(
            source_id=p.source_id,
            document_title=p.document_title,
            page=p.page,
            dense_score=round(p.dense_score, 4) if p.dense_score is not None else None,
            lexical_rank=p.lexical_rank,
            used=p.source_id in cited,
        )
        for p in retrieval.passages
    ]
