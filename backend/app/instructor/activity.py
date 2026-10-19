"""Eğitmen için ders etkinliği: tamamen kayıtlı soru-cevaplardan hesaplanır (sahte veri yok).

Sohbetler henüz kullanıcıya bağlı değil (kimlik doğrulama S02'de); bu yüzden özet anonim ve
ders düzeyindedir.
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Conversation, Document, Message
from app.schemas.instructor import CourseActivity, DailyCount, QuestionItem, SourceUsage

# Grafikteki gün sayısı ve listelerin uzunlukları.
DAYS = 14
TOP_SOURCES = 5
RECENT = 8
UNANSWERED = 6


def course_activity(db: Session, course_id: int, today: date | None = None) -> CourseActivity:
    rows = db.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.course_id == course_id)
        .order_by(Message.conversation_id, Message.id)
    ).scalars()

    questions: list[QuestionItem] = []
    citations: Counter[str] = Counter()
    conversations: set[int] = set()
    pending: Message | None = None
    for message in rows:
        if message.role == "user":
            pending = message
            continue
        if pending is None or pending.conversation_id != message.conversation_id:
            continue
        meta = message.meta or {}
        questions.append(
            QuestionItem(
                question=pending.content, outcome=_outcome(meta), asked_at=pending.created_at
            )
        )
        citations.update(str(source) for source in meta.get("cited_source_ids", []))
        conversations.add(message.conversation_id)
        pending = None

    outcomes = Counter(q.outcome for q in questions)
    newest_first = sorted(questions, key=lambda q: q.asked_at, reverse=True)
    return CourseActivity(
        questions=len(questions),
        conversations=len(conversations),
        answered=outcomes["answered"],
        not_covered=outcomes["insufficient_evidence"],
        not_generated=outcomes["unsupported"] + outcomes["model_refusal"],
        unavailable=outcomes["provider_failure"],
        daily=_daily(questions, today or datetime.now(UTC).date()),
        top_sources=_top_sources(db, citations),
        recent_questions=newest_first[:RECENT],
        unanswered_questions=[
            q for q in newest_first if q.outcome in {"insufficient_evidence", "unsupported"}
        ][:UNANSWERED],
    )


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
