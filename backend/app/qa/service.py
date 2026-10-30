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
from app.llm.gateway import resolve_judge
from app.retrieval.hybrid import retrieve
from app.retrieval.rerank import rerank
from app.retrieval.types import RetrievalResult, VideoPosition
from app.schemas.ask import AskRequest, AskResponse, RetrievalHit, VideoRef

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
    # Cevabın dayandığı arama sonucu (yalnızca `answer_stream`; kaydedilen akışta None).
    retrieval: RetrievalResult | None = None


QAEvent = RetrievalEvent | DeltaEvent | DoneEvent


def get_conversation(
    db: Session, course: Course, conversation_id: int | None, user_id: int | None = None
) -> Conversation:
    """Var olan sohbeti getirir ya da yenisini başlatır.

    Başka dersin ya da başka kullanıcının sohbeti kullanılamaz (CONTRACTS.md §3). `user_id`
    yalnızca değerlendirme hattında (geri alınan işlem) boştur; API her zaman verir.
    """
    if conversation_id is None:
        conversation = Conversation(course_id=course.id, user_id=user_id)
        db.add(conversation)
        db.flush()
        return conversation
    conversation = db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.course_id != course.id
        or conversation.user_id != user_id
    ):
        raise ConversationNotFound(conversation_id)
    return conversation


def ask_stream(
    db: Session,
    course: Course,
    request: AskRequest,
    llm: LLMClient | None,
    embedder: Embedder | None = None,
    user_id: int | None = None,
) -> Iterator[QAEvent]:
    """Önce bulunan parçalar, sonra taslak cevap metni parça parça, en sonda doğrulanmış cevap.

    DeltaEvent'ler doğrulanmamış taslaktır; DoneEvent'teki cevap taslağın yerini alır
    (iddialar çıkarılmış, cevap reddedilmiş ya da LLM'siz alıntıya düşülmüş olabilir).
    LLM'e yalnızca soru, parçalar ve sohbet geçmişi gider; kullanıcı kimliği gitmez (ADR-5).
    """
    conversation = get_conversation(db, course, request.conversation_id, user_id)
    history = conversation_history(db, conversation)

    response: AskResponse | None = None
    for event in answer_stream(
        db, course, request.question, history, llm, video=request.video, embedder=embedder
    ):
        if isinstance(event, DoneEvent):
            response = event.response
        else:
            yield event
    assert response is not None

    response.conversation_id = conversation.id
    db.add_all(
        [
            Message(conversation_id=conversation.id, role="user", content=request.question),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=response.answer or response.decline_reason or "",
                meta=answer_meta(response),
            ),
        ]
    )
    db.commit()
    yield DoneEvent(response)


def answer_stream(
    db: Session,
    course: Course,
    question: str,
    history: list[ChatMessage],
    llm: LLMClient | None,
    video: VideoRef | None = None,
    embedder: Embedder | None = None,
    search_query: str | None = None,
    reranker: LLMClient | None = None,
) -> Iterator[QAEvent]:
    """Kaynaklı cevap hattı (arama → üretim → alıntı doğrulama); hiçbir şey kaydetmez.

    `/ask` ve AI Tutor'un `answer_from_course` aracı bunu kullanır. Son olay DoneEvent'tir.
    `search_query`: aramada sorunun yerine kullanılır (ör. Türkçe soru için materyalin dilinde
    yazılmış ifade); cevap yine öğrencinin sorusuna göre üretilir.
    `reranker`: verilirse geniş aday listesi bu modelle yeniden sıralanır (`retrieval/rerank.py`).
    """
    # Takip sorusu ("peki karmaşıklığı ne?") tek başına eksik kalabilir; önceki soru
    # bağlam olarak ayrıca aranır.
    previous_question = next((m["content"] for m in reversed(history) if m["role"] == "user"), None)
    use_rerank = reranker is not None and settings.tutor_rerank_candidates > 0
    retrieval = retrieve(
        db,
        course,
        search_query or question,
        video=VideoPosition(video.document_id, video.time_s) if video else None,
        k=settings.tutor_rerank_candidates if use_rerank else 5,
        embedder=embedder,
        context=previous_question,
    )
    if use_rerank and retrieval.relevant:
        assert reranker is not None
        query = f"{question}\n({search_query})" if search_query else question
        retrieval.passages = rerank(query, retrieval.passages, reranker, settings.tutor_rerank_keep)
    elif use_rerank:
        retrieval.passages = retrieval.passages[:5]
    yield RetrievalEvent(_hits(retrieval, cited=set()))

    judge, judge_error = (None, None)
    if llm is not None and settings.claim_check == "required" and retrieval.relevant:
        judge, judge_error = resolve_judge()
    response: AskResponse | None = None
    for item in stream_answer(
        course,
        question,
        history,
        retrieval,
        llm,
        judge=judge,
        claim_check=settings.claim_check,
        judge_error=judge_error,
    ):
        if isinstance(item, AskResponse):
            response = item
        else:
            yield DeltaEvent(item)
    assert response is not None

    cited = {c.source_id for c in response.citations}
    response.retrieval = _hits(retrieval, cited)
    response.similarity_threshold = settings.retrieval_min_similarity
    response.best_similarity = retrieval.best_similarity
    yield DoneEvent(response, retrieval)


def answer_meta(response: AskResponse) -> dict:
    """Mesaj kaydındaki cevap özeti; eğitmen etkinliği (`instructor/activity.py`) bunu okur."""
    return {
        "declined": response.declined,
        "outcome": response.outcome,
        "mode": response.mode,
        "model": response.model,
        "cited_source_ids": sorted(c.source_id for c in response.citations),
        # #10: iddia kontrolünün denetim kaydı (hallucination oranı buradan hesaplanır).
        "claim_check": _claim_check_meta(response),
    }


def _claim_check_meta(response: AskResponse) -> dict | None:
    check = response.claim_check
    if check is None:
        return None
    return {
        **check.model_dump(exclude={"records", "error"}),
        "error": check.error,
        "records": check.records,
    }


def ask(
    db: Session,
    course: Course,
    request: AskRequest,
    llm: LLMClient | None,
    embedder: Embedder | None = None,
    user_id: int | None = None,
) -> AskResponse:
    for event in ask_stream(db, course, request, llm, embedder, user_id):
        if isinstance(event, DoneEvent):
            return event.response
    raise RuntimeError("Soru-cevap akışı sonuçsuz bitti")


def conversation_history(db: Session, conversation: Conversation) -> list[ChatMessage]:
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
            t_start=p.t_start,
            t_end=p.t_end,
            dense_score=round(p.dense_score, 4) if p.dense_score is not None else None,
            lexical_rank=p.lexical_rank,
            used=p.source_id in cited,
        )
        for p in retrieval.passages
    ]
