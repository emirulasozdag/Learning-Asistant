"""Eğitmenin asistan cevabını ya da pratik sorusunu onaylaması / düzeltmesi (FR-16, #20).

- Pratik sorusu: `approve` soruyu ve rubriğini eğitmen onaylı yapar (geri çekilmişse yeniden
  yayımlar); `correct` soruyu geri çeker (`withdrawn`), öğrenciye artık sunulmaz.
- Asistan cevabı: karar ve düzeltme saklanır. Yalnızca araştırma kaydını açmış, derste öğrenci
  olan birinin sohbetindeki cevap incelenebilir (eğitmen ancak bu cevapları görür; ADR-4).

Her karar ayrı satırdır; son karar geçerlidir, geçmiş korunur.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Conversation,
    Enrollment,
    InstructorReview,
    Message,
    PracticeQuestion,
    User,
)
from app.schemas.instructor import ReviewDecision, ReviewOut

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
    if message is None or message.role != "assistant":
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
