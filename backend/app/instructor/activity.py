"""Eğitmen için ders etkinliği: tamamen kayıtlı soru-cevaplardan hesaplanır (sahte veri yok).

ADR-4: analitik toplu ve anonimdir, kişi bazlı gösterim yoktur. Yalnızca araştırma kaydını
(`research_logging`) açmış ve derste öğrenci olan kullanıcıların sohbetleri sayılır; kimse
tercihini kapatınca ya da dersten çıkarılınca verisi bir sonraki hesapta düşer.

Küçük grup bastırılır (sayılar ve sorular tek kişiye bağlanamasın): en az `MIN_GROUP` farklı
öğrenciden veri yoksa özet boş döner; bir soru listesi de ancak listedeki sorular en az
`MIN_GROUP` farklı öğrenciden geliyorsa gösterilir.
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Conversation, Document, Enrollment, Message, User
from app.schemas.instructor import CourseActivity, DailyCount, QuestionItem, SourceUsage

# Grafikteki gün sayısı ve listelerin uzunlukları.
DAYS = 14
TOP_SOURCES = 5
RECENT = 8
UNANSWERED = 6
# Soru metinlerinin gösterilmesi için gereken en az farklı öğrenci sayısı.
MIN_GROUP = 3


def course_activity(db: Session, course_id: int, today: date | None = None) -> CourseActivity:
    rows = db.execute(
        select(Message, Conversation.user_id)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .join(User, User.id == Conversation.user_id)
        .join(
            Enrollment,
            (Enrollment.user_id == User.id) & (Enrollment.course_id == Conversation.course_id),
        )
        .where(
            Conversation.course_id == course_id,
            User.research_logging.is_(True),
            Enrollment.role == "student",
        )
        .order_by(Message.conversation_id, Message.id)
    ).all()

    questions: list[QuestionItem] = []
    askers: list[int] = []  # questions ile aynı sırada: soruyu soran öğrenci
    citations: Counter[str] = Counter()
    conversations: set[int] = set()
    students: set[int] = set()
    pending: Message | None = None
    for message, user_id in rows:
        if message.role == "user":
            pending = message
            continue
        if pending is None or pending.conversation_id != message.conversation_id:
            continue
        meta = message.meta or {}
        if meta.get("counted") is False:
            # AI Tutor'da kaynaklı cevap içermeyen tur (selamlaşma, netleştirme): soru değil.
            pending = None
            continue
        questions.append(
            QuestionItem(
                question=pending.content, outcome=_outcome(meta), asked_at=pending.created_at
            )
        )
        askers.append(user_id)
        citations.update(str(source) for source in meta.get("cited_source_ids", []))
        conversations.add(message.conversation_id)
        students.add(user_id)
        pending = None

    today = today or datetime.now(UTC).date()
    if len(students) < MIN_GROUP:
        return _empty(today)
    outcomes = Counter(q.outcome for q in questions)
    newest_first = sorted(zip(questions, askers, strict=True), key=lambda p: p[0].asked_at)[::-1]
    unanswered = [
        p for p in newest_first if p[0].outcome in {"insufficient_evidence", "unsupported"}
    ]
    return CourseActivity(
        questions=len(questions),
        conversations=len(conversations),
        answered=outcomes["answered"],
        not_covered=outcomes["insufficient_evidence"],
        not_generated=outcomes["unsupported"] + outcomes["model_refusal"],
        unavailable=outcomes["provider_failure"] + outcomes["verification_failure"],
        daily=_daily(questions, today),
        top_sources=_top_sources(db, citations),
        recent_questions=_group_safe(newest_first[:RECENT]),
        unanswered_questions=_group_safe(unanswered[:UNANSWERED]),
    )


def _empty(today: date) -> CourseActivity:
    return CourseActivity(
        questions=0,
        conversations=0,
        answered=0,
        not_covered=0,
        not_generated=0,
        unavailable=0,
        daily=_daily([], today),
        top_sources=[],
        recent_questions=[],
        unanswered_questions=[],
    )


def _group_safe(items: list[tuple[QuestionItem, int]]) -> list[QuestionItem]:
    """Liste en az MIN_GROUP farklı öğrencinin sorusunu içermiyorsa gösterilmez."""
    if len({asker for _, asker in items}) < MIN_GROUP:
        return []
    return [question for question, _ in items]


def _outcome(meta: dict) -> str:
    """#5 öncesi kayıtlarda `outcome` yok; o zaman yalnızca ret bilgisi vardır."""
    if outcome := meta.get("outcome"):
        return str(outcome)
    return "insufficient_evidence" if meta.get("declined") else "answered"


def _daily(questions: list[QuestionItem], today: date) -> list[DailyCount]:
    counts = Counter(q.asked_at.astimezone(UTC).date() for q in questions)
    days = [today - timedelta(days=DAYS - 1 - offset) for offset in range(DAYS)]
    return [DailyCount(day=day, questions=counts[day]) for day in days]


def _top_sources(db: Session, citations: Counter[str]) -> list[SourceUsage]:
    ids = [int(source) for source, _ in citations.most_common(TOP_SOURCES) if source.isdigit()]
    if not ids:
        return []
    found = {
        str(chunk.id): (chunk, document)
        for chunk, document in db.execute(
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id.in_(ids))
        ).all()
    }
    return [
        SourceUsage(
            source_id=source,
            document_title=found[source][1].title,
            page=found[source][0].page,
            citations=count,
        )
        for source, count in citations.most_common(TOP_SOURCES)
        if source in found
    ]
