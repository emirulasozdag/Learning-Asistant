import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Conversation, Course, Document, Message, User, VideoFrame
from app.embeddings.base import Embedder
from app.generation.answer import stream_answer
from app.generation.visual import StoredFrameSource, VisualContext
from app.llm.base import ChatMessage, LLMClient
from app.llm.gateway import resolve_judge
from app.retrieval.hybrid import retrieve
from app.retrieval.rerank import rerank
from app.retrieval.types import RetrievalResult, VideoPosition
from app.schemas.ask import (
    AskRequest,
    AskResponse,
    RetrievalHit,
    VideoContextOut,
    VideoMomentOut,
    VideoRef,
)
from app.sources.lookup import to_frame_ref

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
    # populate_existing: oturumda yüklü kopya yerine veritabanına bakılır. Uzun bir tur sırasında
    # silinen sohbet böylece "bulunamadı" olur (#88).
    conversation = db.get(Conversation, conversation_id, populate_existing=True)
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
    frames: bool = True,
) -> Iterator[QAEvent]:
    """Önce bulunan parçalar, sonra taslak cevap metni parça parça, en sonda doğrulanmış cevap.

    DeltaEvent'ler doğrulanmamış taslaktır; DoneEvent'teki cevap taslağın yerini alır
    (iddialar çıkarılmış, cevap reddedilmiş ya da LLM'siz alıntıya düşülmüş olabilir).
    LLM'e yalnızca soru, parçalar ve sohbet geçmişi gider; video verildiyse durdurulan anın
    kareleri de (üreticiye türetilmiş metin, judge'a görüntü; ADR-12). Kullanıcı kimliği gitmez
    (ADR-5).
    """
    # Var olan sohbet yalnızca okunur; yenisi cevapla birlikte yazılır. Uzun üretim (LLM,
    # judge) sırasında açık bir veritabanı işlemi kalmaz (#21): arama bitince işlem kapatılır.
    conversation = (
        get_conversation(db, course, request.conversation_id, user_id)
        if request.conversation_id is not None
        else None
    )
    history = conversation_history(db, conversation) if conversation is not None else []

    response: AskResponse | None = None
    for event in answer_stream(
        db,
        course,
        request.question,
        history,
        llm,
        video=request.video,
        embedder=embedder,
        release=db.commit,
        frames=frames,
    ):
        if isinstance(event, DoneEvent):
            response = event.response
        else:
            yield event
    assert response is not None

    # Sohbet üretim sürerken silindiyse ConversationNotFound; yeni sohbet burada açılır.
    conversation = get_conversation(db, course, request.conversation_id, user_id)
    response.conversation_id = conversation.id
    logged = research_logging_now(db, user_id)
    db.add_all(
        [
            Message(
                conversation_id=conversation.id,
                role="user",
                content=request.question,
                research_logged=logged,
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content=response.transcript_text,
                meta={**answer_meta(response), "video": video_trace(response.video_context)},
                research_logged=logged,
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
    release: Callable[[], None] | None = None,
    frames: bool = True,
) -> Iterator[QAEvent]:
    """Kaynaklı cevap hattı (arama → üretim → alıntı doğrulama); hiçbir şey kaydetmez.

    `/ask` ve AI Tutor'un `answer_from_course` aracı bunu kullanır. Son olay DoneEvent'tir.
    `search_query`: aramada sorunun yerine kullanılır (ör. Türkçe soru için materyalin dilinde
    yazılmış ifade); cevap yine öğrencinin sorusuna göre üretilir.
    `reranker`: verilirse geniş aday listesi bu modelle yeniden sıralanır (`retrieval/rerank.py`).
    `release`: verilirse aramadan hemen sonra çağrılır (ör. `db.commit`); model çağrıları açık
    bir veritabanı işlemi içinde beklemez.
    `frames`: False ise durdurulan anın kareleri cevaba girmez (yalnızca transkript). Ürün her
    zaman True kullanır; değerlendirme transcript-only ve görsel koşulu ayırmak için kapatır (#30).
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
    # Doğrulanmış video bağlamı (#25) ve durdurulan anın kareleri (#26) model çağrılarından önce,
    # aynı okuma işleminde okunur. Kareler yalnızca model cevap yazacaksa yüklenir.
    context = video_context(db, video)
    visual = (
        frame_context(db, course, video)
        if frames and llm is not None and retrieval.relevant and retrieval.passages
        else None
    )
    if release is not None:
        release()
    # Durdurulan andaki bölüm (#102) yeniden sıralamaya girmez, her zaman başta kalır.
    moment = retrieval.video_moment
    pinned = [p for p in retrieval.passages if moment and p.source_id in moment.source_ids]
    others = [p for p in retrieval.passages if not moment or p.source_id not in moment.source_ids]
    if use_rerank and retrieval.relevant:
        assert reranker is not None
        query = f"{question}\n({search_query})" if search_query else question
        retrieval.passages = pinned + rerank(query, others, reranker, settings.tutor_rerank_keep)
    elif use_rerank:
        retrieval.passages = pinned + others[:5]
    yield RetrievalEvent(_hits(retrieval, cited=set()))

    judge, judge_error = (None, None)
    if llm is not None and settings.claim_check == "required" and retrieval.relevant:
        judge, judge_error = resolve_judge()
    response: AskResponse | None = None
    for item in stream_answer(
        course,
        _with_moment(question, retrieval),
        history,
        retrieval,
        llm,
        judge=judge,
        claim_check=settings.claim_check,
        judge_error=judge_error,
        # "Burayı anlamadım" + durdurulan an: özet değil, o anı öğreten açıklama (#103).
        explain=moment is not None and retrieval.deictic,
        visual=visual,
    ):
        if isinstance(item, AskResponse):
            response = item
        else:
            yield DeltaEvent(item)
    assert response is not None

    cited = {c.source_id for c in response.citations}
    response.retrieval = _hits(retrieval, cited)
    if moment is not None:
        response.video_moment = VideoMomentOut(
            document_id=moment.document_id,
            document_title=moment.document_title,
            t_start=moment.t_start,
            t_end=moment.t_end,
            deictic=retrieval.deictic,
        )
    response.video_context = context
    response.similarity_threshold = settings.retrieval_min_similarity
    response.best_similarity = retrieval.best_similarity
    yield DoneEvent(response, retrieval)


def video_context(db: Session, video: VideoRef | None) -> VideoContextOut | None:
    """İsteğin doğrulanmış video bağlamı (#25): video varlığı, kırpılmış an ve o andaki kare.

    `video` API katmanında doğrulanmıştır (`api.deps.checked_video`); bu yalnızca okur. Video ya
    da kare istek sürerken silindiyse ilgili alan boş kalır.
    """
    if video is None:
        return None
    document = db.get(Document, video.document_id)
    frame = db.get(VideoFrame, video.frame_id) if video.frame_id is not None else None
    if frame is not None and frame.document_id != video.document_id:
        frame = None
    return VideoContextOut(
        document_id=video.document_id,
        media_sha256=document.media_sha256 if document else None,
        duration_s=document.duration_s if document else None,
        time_s=video.time_s,
        frame=to_frame_ref(frame) if frame is not None else None,
    )


def frame_context(db: Session, course: Course, video: VideoRef | None) -> VisualContext | None:
    """Cevaba girecek kareler (#26, ADR-12): durdurulan andaki (ya da öğrencinin seçtiği) kare ve
    çevresindeki kareler, en çok `MAX_FRAMES`.

    `video` API katmanında doğrulanmıştır (`api.deps.checked_video`); `StoredFrameSource` yine
    yalnızca bu dersin onaylı ve hazır video dokümanlarının karelerini okur. Video yoksa None.
    """
    if video is None:
        return None
    return StoredFrameSource(db, course).moment(
        VideoPosition(video.document_id, video.time_s), frame_id=video.frame_id
    )


def video_trace(context: VideoContextOut | None) -> dict | None:
    """Mesaj kaydına yazılan video bağlamı (#25): kimlikler ve zamanlar. Kare görüntüsü ve
    türetilmiş metin (OCR, betimleme) kayda girmez; kare kendi tablosunda kalır."""
    if context is None:
        return None
    frame = context.frame
    return {
        "document_id": context.document_id,
        "media_sha256": context.media_sha256,
        "time_s": context.time_s,
        "frame_id": frame.frame_id if frame else None,
        "frame": (
            {"t_start": frame.t_start, "t_end": frame.t_end, "t_frame": frame.t_frame}
            if frame
            else None
        ),
    }


def research_logging_now(db: Session, user_id: int | None) -> bool:
    """Kullanıcının araştırma kaydı tercihi, mesaj yazıldığı an (ADR-4, #104).

    Veritabanından taze okunur: tur sürerken tercih değiştiyse yazım anındaki geçerlidir.
    """
    if user_id is None:
        return False
    user = db.get(User, user_id, populate_existing=True)
    return bool(user and user.research_logging)


def answer_meta(response: AskResponse) -> dict:
    """Mesaj kaydındaki cevap özeti; eğitmen etkinliği (`instructor/activity.py`) bunu okur."""
    meta = {
        "declined": response.declined,
        "outcome": response.outcome,
        "mode": response.mode,
        "model": response.model,
        "cited_source_ids": sorted(c.source_id for c in response.citations),
        # #10: iddia kontrolünün denetim kaydı (hallucination oranı buradan hesaplanır).
        "claim_check": _claim_check_meta(response),
    }
    if response.visual is not None:
        # #26 (ADR-12): cevaba giren kareler, görüntüsü judge'a gidenler, kalan kare alıntıları;
        # yalnızca kimlikler ve zamanlar. Kare verilmeyen cevabın kaydı önceki gibidir.
        meta["visual"] = response.visual.model_dump()
    if response.visual_gap is not None:
        # #30: görsel kanıtın neden yetmediği (eğitmen etkinliği ve değerlendirme için).
        meta["visual_gap"] = response.visual_gap
    return meta


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
    frames: bool = True,
) -> AskResponse:
    for event in ask_stream(db, course, request, llm, embedder, user_id, frames=frames):
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
            video_moment=bool(
                retrieval.video_moment and p.source_id in retrieval.video_moment.source_ids
            ),
        )
        for p in retrieval.passages
    ]


def _with_moment(question: str, retrieval: RetrievalResult) -> str:
    """Modele, öğrencinin videoyu nerede durdurduğunu söyler (#102): "burası" o bölümdür.
    Öğrenciye gösterilen soru değişmez; yalnızca üretim isteminde kullanılır."""
    moment = retrieval.video_moment
    if moment is None:
        return question
    span = f"{_clock(moment.t_start)}–{_clock(moment.t_end)}"
    note = (
        f'(Öğrenci "{moment.document_title}" videosunu {span} aralığında izlerken durdurdu; '
        f"{_first_labels(len(moment.source_ids))} o anda anlatılan bölümdür (zamanlarına bak)."
    )
    if retrieval.deictic:
        note += (
            ' Sorudaki "burası, bu kısım, bunu" gibi ifadeler bu bölümü kasteder; önce onu açıkla.'
        )
    return f"{question}\n\n{note})"


def _first_labels(count: int) -> str:
    """Sabitlenen bölüm kaynakların başındadır: S1, S1–S2, S1–S3."""
    return "S1 kaynağı" if count <= 1 else f"S1–S{count} kaynakları"


def _clock(seconds: float) -> str:
    total = int(seconds)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"
