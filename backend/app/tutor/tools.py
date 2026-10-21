"""AI Tutor araçları: orkestratörün çağırabildiği tipli iş akışları (ADR-7).

Her araç öğrenciye görünen blokları kendisi üretir ve orkestratöre yalnızca kısa bir durum
(`ToolOutcome`) döndürür; öğretim içeriği orkestratörden geçmez. Kurallar kodda zorlanır:
- `explain_general` yalnızca bu turda `answer_from_course` "not_covered" döndürdüyse ve
  genel bilgi açıksa çalışır.
- Turu bitiren araçlardan (`finish`, `ask_clarification`, `reply_notice`) sonra başka araç
  çalışmaz.
"""

import time
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.models import Course, User
from app.embeddings.base import Embedder
from app.generation.general import GeneralExplanation, stream_general_explanation
from app.llm.base import ChatMessage, LLMClient, ToolSpec
from app.practice import service as practice
from app.qa.service import DeltaEvent, DoneEvent, RetrievalEvent, answer_stream
from app.retrieval.types import RetrievedPassage
from app.schemas.ask import AskResponse, RetrievalHit, VideoRef
from app.schemas.practice import PracticeType
from app.schemas.tutor import (
    ClarificationBlock,
    CourseAnswerBlock,
    FollowUp,
    FollowUpAction,
    FollowUpsBlock,
    GeneralExplanationBlock,
    NoticeBlock,
    NoticeKind,
    PracticeBlock,
    ToolTrace,
    TutorBlock,
)

# Bir turda en fazla bu kadar kaynaklı cevap (birden fazla ayrı soru içeren mesaj için).
MAX_COURSE_ANSWERS = 2

NOTICES: dict[NoticeKind, str] = {
    "greeting": (
        "Merhaba! {course} dersiyle ilgili sorularını ders materyaline dayanarak cevaplayabilirim."
    ),
    "off_topic": (
        "Bu istek {course} dersinin kapsamı dışında görünüyor. Ders konularıyla ilgili bir "
        "soru sorabilirsin."
    ),
    "graded_work": (
        "Not verilen ödev ya da sınav sorularının cevabını veremem. Konuyu birlikte "
        "çalışabiliriz: hangi kavramı anlamakta zorlanıyorsun?"
    ),
    "not_covered": "Bu konu ders materyalinde yer almıyor.",
    "unavailable": (
        "Bu özellik henüz hazır değil. Şimdilik ders materyaliyle ilgili soru sorabilirsin."
    ),
    "failure": "Bu adım tamamlanamadı; lütfen tekrar dene.",
}

FOLLOW_UPS: dict[FollowUpAction, FollowUp] = {
    "simpler": FollowUp(
        action="simpler", label="Daha basit anlat", message="Bunu daha basit anlatır mısın?"
    ),
    "example": FollowUp(
        action="example", label="Örnekle göster", message="Bunu bir örnekle gösterir misin?"
    ),
}


# --- Akış olayları -----------------------------------------------------------------------------


@dataclass
class StatusEvent:
    """Bir araç çalışmaya başladı (arayüzde "Ders materyalinde aranıyor…")."""

    tool: str
    label: str


@dataclass
class RetrievalHitsEvent:
    block_index: int
    hits: list[RetrievalHit]


@dataclass
class DraftEvent:
    """Doğrulanmamış taslak metin; aynı `block_index`'teki blok gelince yerini alır."""

    block_index: int
    text: str


@dataclass
class BlockEvent:
    index: int
    block: TutorBlock


TutorEvent = StatusEvent | RetrievalHitsEvent | DraftEvent | BlockEvent


# --- Tur bağlamı ve araç tanımı ---------------------------------------------------------------


@dataclass
class TurnContext:
    db: Session
    course: Course
    message: str
    history: list[ChatMessage]
    generator: LLMClient | None
    # Bağımsız kontrolcü (pratik sorusunu anahtarsız çözer) ve isteyen kullanıcı.
    checker: LLMClient | None = None
    reranker: LLMClient | None = None
    user: User | None = None
    # Sohbetteki son kaynaklı cevabın alıntıladığı parçalar ("bu konuda beni test et").
    recent_source_ids: list[str] = field(default_factory=list)
    conversation_id: int | None = None
    video: VideoRef | None = None
    embedder: Embedder | None = None
    general_enabled: bool = False
    blocks: list[TutorBlock] = field(default_factory=list)
    course_responses: list[AskResponse] = field(default_factory=list)
    # Bu turda materyalde bulunamayan sorular ve en yakın parçalar (genel açıklama bağlamı).
    not_covered: list[str] = field(default_factory=list)
    nearest_passages: list[RetrievedPassage] = field(default_factory=list)
    finished: bool = False
    steps: list[ToolTrace] = field(default_factory=list)

    def add_block(self, block: TutorBlock) -> Generator[TutorEvent, None, None]:
        self.blocks.append(block)
        yield BlockEvent(len(self.blocks) - 1, block)


@dataclass
class ToolOutcome:
    """Orkestratöre bildirilen sonuç. Öğretim içeriği taşımaz; yalnızca karar için durum."""

    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_result(self) -> dict[str, Any]:
        return {"status": self.status, **self.detail}


ToolHandler = Callable[[TurnContext, Any], Generator[TutorEvent, None, ToolOutcome]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    label: str
    handler: ToolHandler
    ends_turn: bool = False

    def spec(self) -> ToolSpec:
        return ToolSpec(self.name, self.description, self.params.model_json_schema())

    def run(self, ctx: TurnContext, args: BaseModel) -> Generator[TutorEvent, None, ToolOutcome]:
        yield StatusEvent(self.name, self.label)
        started = time.monotonic()
        outcome = yield from self.handler(ctx, args)
        ctx.steps.append(
            ToolTrace(
                tool=self.name,
                args=args.model_dump(),
                status=outcome.status,
                duration_ms=round((time.monotonic() - started) * 1000),
            )
        )
        if self.ends_turn:
            ctx.finished = True
        return outcome


# --- Araçlar -----------------------------------------------------------------------------------


class QuestionArgs(BaseModel):
    question: str = Field(
        min_length=1,
        max_length=2000,
        description=(
            "Öğrencinin sorusu, tek başına anlaşılır biçimde. Takip sorusunu önceki konuşmayla "
            "tamamla; öğrencinin dilini koru; yeni bilgi ekleme."
        ),
    )


class CourseQuestionArgs(QuestionArgs):
    search_query: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Sorunun ders materyalinin dilindeki karşılığı: anahtar kelime listesi değil, doğal ve "
            "açık bir soru cümlesi; terimleri materyaldeki gibi yaz (ör. 'Why does binary search "
            "run in logarithmic time on a sorted array?'). Materyal öğrencinin dilindeyse boş "
            "bırak."
        ),
    )


def _answer_from_course(
    ctx: TurnContext, args: CourseQuestionArgs
) -> Generator[TutorEvent, None, ToolOutcome]:
    if len(ctx.course_responses) >= MAX_COURSE_ANSWERS:
        return ToolOutcome("rejected", {"reason": "Bu turda yeterince kaynaklı cevap verildi."})
    index = len(ctx.blocks)
    response: AskResponse | None = None
    for event in answer_stream(
        ctx.db,
        ctx.course,
        args.question,
        ctx.history,
        ctx.generator,
        video=ctx.video,
        embedder=ctx.embedder,
        search_query=args.search_query,
        reranker=ctx.reranker,
    ):
        if isinstance(event, RetrievalEvent):
            yield RetrievalHitsEvent(index, event.hits)
        elif isinstance(event, DeltaEvent):
            yield DraftEvent(index, event.text)
        elif isinstance(event, DoneEvent):
            response = event.response
            if response.outcome == "insufficient_evidence" and event.retrieval is not None:
                ctx.not_covered.append(args.question)
                ctx.nearest_passages = event.retrieval.passages
    assert response is not None
    response.conversation_id = ctx.conversation_id
    ctx.course_responses.append(response)
    yield from ctx.add_block(CourseAnswerBlock(response=response))

    if response.outcome == "insufficient_evidence":
        general = ctx.general_enabled and ctx.generator is not None
        return ToolOutcome("not_covered", {"general_explanation_available": general})
    return ToolOutcome(
        response.outcome,
        {
            "citations": len(response.citations),
            "sources": sorted({c.document_title for c in response.citations}),
        },
    )


def _explain_general(
    ctx: TurnContext, args: QuestionArgs
) -> Generator[TutorEvent, None, ToolOutcome]:
    if not ctx.not_covered or ctx.generator is None:
        return ToolOutcome(
            "rejected",
            {"reason": "Yalnızca answer_from_course bu turda 'not_covered' döndürdüyse."},
        )
    index = len(ctx.blocks)
    drafted = False
    result: GeneralExplanation | None = None
    for item in stream_general_explanation(
        ctx.course, args.question, ctx.history, ctx.nearest_passages, ctx.generator
    ):
        if isinstance(item, GeneralExplanation):
            result = item
        else:
            drafted = True
            yield DraftEvent(index, item)
    assert result is not None
    if result.outcome == "explained" and result.text:
        yield from ctx.add_block(GeneralExplanationBlock(text=result.text, model=result.model))
    elif drafted:
        # Akmış taslak doğrulanmış bir blokla değiştirilmeli; boş kalmasın.
        yield from ctx.add_block(NoticeBlock(kind="failure", text=NOTICES["failure"]))
    return ToolOutcome(result.outcome)


class PracticeArgs(BaseModel):
    topic: str = Field(
        min_length=1,
        max_length=300,
        description=(
            "Sorunun konusu, öğrencinin dilinde kısa bir ifade: öğrencinin belirttiği ya da "
            "konuşmadaki son ders konusu. Materyalin dilindeki karşılığı `search_query`'ye."
        ),
    )
    type: Literal["mcq", "short_answer", "code_tracing"] = Field(
        default="mcq", description="Öğrenci belirtmediyse mcq."
    )
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    language: Literal["tr", "en"] = Field(default="tr", description="Öğrencinin yazdığı dil.")
    search_query: str | None = Field(
        default=None,
        max_length=300,
        description=(
            "Konunun ders materyalinin dilindeki karşılığı, materyaldeki terimlerle (ör. 'binary "
            "search on a sorted array'). Materyal öğrencinin dilindeyse boş bırak."
        ),
    )


def _generate_practice(
    ctx: TurnContext, args: PracticeArgs
) -> Generator[TutorEvent, None, ToolOutcome]:
    if ctx.user is None:
        return ToolOutcome("rejected", {"reason": "Pratik için oturum gerekli."})
    # Bu turda ya da hemen önce okunan cevabın kaynakları önce denenir.
    this_turn = [c.source_id for r in ctx.course_responses for c in r.citations]
    steps = practice.create_question_steps(
        ctx.db,
        ctx.course,
        ctx.user,
        PracticeType(args.type),
        args.difficulty,
        practice.PracticeContext(
            topic=args.topic,
            search_query=args.search_query,
            preferred_source_ids=this_turn or ctx.recent_source_ids,
        ),
        ctx.generator,
        ctx.checker,
        language=args.language,
        embedder=ctx.embedder,
        reranker=ctx.reranker,
    )
    try:
        while True:
            yield StatusEvent(GENERATE_PRACTICE_NAME, next(steps))
    except StopIteration as done:
        question = done.value
    except practice.NoValidItem as exc:
        yield from ctx.add_block(NoticeBlock(kind="not_covered", text=exc.reason))
        return ToolOutcome("no_valid_item")
    yield from ctx.add_block(PracticeBlock(item=practice.to_item(question)))
    # Anahtar, referans cevap ve açıklama orkestratöre de gitmez.
    return ToolOutcome("created", {"type": args.type, "topic": question.topic})


GENERATE_PRACTICE_NAME = "generate_practice"


class ClarificationArgs(BaseModel):
    question: str = Field(max_length=300, description="Öğrenciye sorulacak kısa soru.")
    options: list[str] = Field(
        default=[], max_length=4, description="En fazla 4 kısa seçenek (isteğe bağlı)."
    )


def _ask_clarification(
    ctx: TurnContext, args: ClarificationArgs
) -> Generator[TutorEvent, None, ToolOutcome]:
    options = [option.strip()[:80] for option in args.options if option.strip()]
    yield from ctx.add_block(ClarificationBlock(question=args.question.strip(), options=options))
    return ToolOutcome("asked")


class NoticeArgs(BaseModel):
    kind: Literal["greeting", "off_topic", "graded_work", "unavailable"] = Field(
        description=(
            "greeting: selamlaşma/teşekkür · off_topic: dersle ilgisiz istek · graded_work: not "
            "verilecek ödev/sınav sorusunun cevabını isteme · unavailable: henüz olmayan "
            "yetenek (sesli kullanım, animasyon)"
        )
    )


def _reply_notice(ctx: TurnContext, args: NoticeArgs) -> Generator[TutorEvent, None, ToolOutcome]:
    text = NOTICES[args.kind].format(course=ctx.course.name)
    yield from ctx.add_block(NoticeBlock(kind=args.kind, text=text))
    return ToolOutcome("shown")


class FinishArgs(BaseModel):
    follow_ups: list[FollowUpAction] = Field(
        default=[],
        max_length=2,
        description="Kaynaklı cevaptan sonra önerilecek adımlar (isteğe bağlı).",
    )


def _finish(ctx: TurnContext, args: FinishArgs) -> Generator[TutorEvent, None, ToolOutcome]:
    answered = any(r.outcome == "answered" for r in ctx.course_responses)
    if answered and args.follow_ups:
        items = [FOLLOW_UPS[action] for action in dict.fromkeys(args.follow_ups)]
        yield from ctx.add_block(FollowUpsBlock(items=items))
    return ToolOutcome("finished")


ANSWER_FROM_COURSE = Tool(
    name="answer_from_course",
    description=(
        "Ders materyalinde arar ve alıntılı, doğrulanmış bir cevap üretir; materyal yetmezse "
        "'not_covered' döner. Ders konusuyla ilgili her soru, açıklama, 'daha basit anlat' ve "
        "'örnekle göster' isteği için kullan."
    ),
    params=CourseQuestionArgs,
    label="Ders materyalinde aranıyor…",
    handler=_answer_from_course,
)
EXPLAIN_GENERAL = Tool(
    name="explain_general",
    description=(
        "Ders materyalinde olmayan ama dersin alanı içindeki bir soruya 'genel bilgi' etiketli "
        "kısa açıklama yazar. Yalnızca answer_from_course 'not_covered' döndükten sonra."
    ),
    params=QuestionArgs,
    label="Genel bilgi açıklaması hazırlanıyor…",
    handler=_explain_general,
)
GENERATE_PRACTICE = Tool(
    name=GENERATE_PRACTICE_NAME,
    description=(
        "Ders materyalinden, otomatik kontrol edilmiş bir pratik sorusu üretir (çoktan seçmeli, "
        "kısa cevap ya da code tracing). Öğrenci soru, test, alıştırma ya da kendini sınamak "
        "istediğinde kullan. Öğrenci cevabını arayüzden gönderir; sen değerlendirmezsin."
    ),
    params=PracticeArgs,
    label="Pratik sorusu hazırlanıyor ve kontrol ediliyor…",
    handler=_generate_practice,
    ends_turn=True,
)
ASK_CLARIFICATION = Tool(
    name="ask_clarification",
    description="Mesaj ne sorulduğu anlaşılmayacak kadar belirsizse öğrenciye kısa soru sorar.",
    params=ClarificationArgs,
    label="Soru netleştiriliyor…",
    handler=_ask_clarification,
    ends_turn=True,
)
REPLY_NOTICE = Tool(
    name="reply_notice",
    description="Sabit metinli kısa bilgilendirme gösterir ve turu bitirir.",
    params=NoticeArgs,
    label="Yanıt hazırlanıyor…",
    handler=_reply_notice,
    ends_turn=True,
)
FINISH = Tool(
    name="finish",
    description="Turu bitirir. Cevap verildiyse en son çağır.",
    params=FinishArgs,
    label="Tamamlanıyor…",
    handler=_finish,
    ends_turn=True,
)


def available_tools(ctx: TurnContext) -> list[Tool]:
    tools = [ANSWER_FROM_COURSE]
    if ctx.general_enabled and ctx.generator is not None:
        tools.append(EXPLAIN_GENERAL)
    if ctx.generator is not None and ctx.checker is not None and ctx.user is not None:
        tools.append(GENERATE_PRACTICE)
    return [*tools, ASK_CLARIFICATION, REPLY_NOTICE, FINISH]
