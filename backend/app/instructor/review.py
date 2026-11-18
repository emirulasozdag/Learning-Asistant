"""Eğitmenin asistan cevabını ya da pratik sorusunu onaylaması / düzeltmesi (FR-16, #20).

- Pratik sorusu: `approve` soruyu ve rubriğini eğitmen onaylı yapar (geri çekilmişse yeniden
  yayımlar); `correct` soruyu geri çeker (`withdrawn`), öğrenciye artık sunulmaz.
- Asistan cevabı: karar ve düzeltme saklanır. Yalnızca araştırma kaydı açıkken yazılmış
  (`research_logged`, #104) ve kaydı hâlâ açık, derste öğrenci olan birinin cevabı incelenebilir
  (eğitmen ancak bu cevapları görür; ADR-4).

Her karar ayrı satırdır; son karar geçerlidir, geçmiş korunur.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import (
    Chunk,
    Conversation,
    Enrollment,
    InstructorReview,
    Message,
    PracticeQuestion,
    User,
)
from app.practice.service import citation, reference_answer
from app.schemas.instructor import LatestReview, PracticeItemReview, ReviewDecision, ReviewOut
from app.schemas.practice import PracticeType

# Eğitmenin inceleme listesinde gösterilen en fazla soru (en yeniler).
MAX_PRACTICE_ITEMS = 50

# Eğitmenin inceleyebileceği pratik soruları: otomatik kontrolün reddettikleri öğrenciye hiç
# gitmediği için inceleme hedefi değildir.
REVIEWABLE_STATUSES = {"released", "withdrawn"}


@dataclass
class ReviewTarget:
    course_id: int
    message: Message | None = None
    question: PracticeQuestion | None = None


def resolve_target(db: Session, decision: ReviewDecision) -> ReviewTarget | None:
    """Kararın hedefi ve dersi; hedef yoksa ya da incelenemezse None (API: 404)."""
    if decision.target_type == "practice_item":
        question = db.get(PracticeQuestion, decision.target_id)
        if question is None or question.status not in REVIEWABLE_STATUSES:
            return None
        return ReviewTarget(course_id=question.course_id, question=question)

    message = db.get(Message, decision.target_id)
    if message is None or message.role != "assistant" or not message.research_logged:
        return None
    row = db.execute(
        select(Conversation.course_id)
        .join(User, User.id == Conversation.user_id)
        .join(
            Enrollment,
            (Enrollment.user_id == User.id) & (Enrollment.course_id == Conversation.course_id),
        )
        .where(
            Conversation.id == message.conversation_id,
            User.research_logging.is_(True),
            Enrollment.role == "student",
        )
    ).first()
    if row is None:
        return None
    return ReviewTarget(course_id=row.course_id, message=message)


def apply_review(
    db: Session, reviewer: User, decision: ReviewDecision, target: ReviewTarget
) -> ReviewOut:
    question = target.question
    if question is not None:
        rubric = question.rubric
        if decision.decision == "approve":
            question.status = "released"
            if rubric is not None:
                rubric.approved = True
                rubric.approved_by = reviewer.id
                rubric.approved_at = datetime.now(UTC)
        else:
            question.status = "withdrawn"
            if rubric is not None:
                rubric.approved = False

    review = InstructorReview(
        course_id=target.course_id,
        target_type=decision.target_type,
        message_id=target.message.id if target.message is not None else None,
        question_id=question.id if question is not None else None,
        decision=decision.decision,
        correction=decision.correction,
        reviewer_id=reviewer.id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)  # created_at sunucuda atanır
    return ReviewOut(
        id=review.id,
        target_type=decision.target_type,
        target_id=decision.target_id,
        decision=decision.decision,
        correction=review.correction,
        created_at=review.created_at,
    )


def list_practice_items(db: Session, course_id: int) -> list[PracticeItemReview]:
    """Dersin öğrencilere sunulmuş (ya da eğitmenin geri çektiği) son pratik soruları."""
    questions = db.scalars(
        select(PracticeQuestion)
        .where(
            PracticeQuestion.course_id == course_id,
            PracticeQuestion.status.in_(REVIEWABLE_STATUSES),
        )
        .options(
            joinedload(PracticeQuestion.rubric),
            joinedload(PracticeQuestion.chunk).joinedload(Chunk.document),
        )
        .order_by(PracticeQuestion.created_at.desc(), PracticeQuestion.id.desc())
        .limit(MAX_PRACTICE_ITEMS)
    ).all()
    latest: dict[int, InstructorReview] = {}
    if questions:
        reviews = db.scalars(
            select(InstructorReview)
            .where(InstructorReview.question_id.in_([q.id for q in questions]))
            .order_by(InstructorReview.id)
        ).all()
        latest = {review.question_id: review for review in reviews if review.question_id}
    consenting = _consenting_requesters(db, questions)
    items = []
    for question in questions:
        mcq = question.type == PracticeType.MCQ
        review = latest.get(question.id)
        items.append(
            PracticeItemReview(
                id=question.id,
                type=PracticeType(question.type),
                topic=question.topic if _topic_visible(question, consenting) else None,
                difficulty=question.difficulty,  # type: ignore[arg-type]
                prompt=question.prompt,
                options=question.options,
                correct_option=int(question.answer_key["correct_option"]) if mcq else None,
                reference_answer=None if mcq else reference_answer(question),
                explanation=question.explanation,
                status=question.status,  # type: ignore[arg-type]
                rubric_approved=bool(question.rubric and question.rubric.approved),
                source=citation(question.chunk),
                created_at=question.created_at,
                latest_review=(
                    LatestReview(
                        decision=review.decision,  # type: ignore[arg-type]
                        correction=review.correction,
                        created_at=review.created_at,
                    )
                    if review
                    else None
                ),
            )
        )
    return items


def _consenting_requesters(db: Session, questions: list[PracticeQuestion]) -> set[int]:
    """Soruları isteyenlerden araştırma kaydı şu an açık olanlar."""
    ids = {q.requested_by for q in questions if q.requested_by is not None}
    if not ids:
        return set()
    return set(db.scalars(select(User.id).where(User.id.in_(ids), User.research_logging.is_(True))))


def _topic_visible(question: PracticeQuestion, consenting: set[int]) -> bool:
    """Konu öğrenciden gelir (yazdığı konu ya da takip sorusunda eksik kavramları); ADR-4 (#104).

    - Takip sorusunun konusu öğrencinin eksikleridir: hiç gösterilmez.
    - Öğrencinin istediği konu yalnızca soru üretilirken ve şu an araştırma kaydı açıksa görünür.
    """
    if question.follow_up_of_attempt_id is not None:
        return False
    return question.research_logged and question.requested_by in consenting
