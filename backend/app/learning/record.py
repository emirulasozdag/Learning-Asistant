"""Öğrencinin kendi öğrenme kaydı (FR-15, #20): pratik denemeleri ve kavram bazında ilerleme.

ADR-4: kayda yalnızca araştırma kaydı açıkken yapılan denemeler (`research_logged`) girer.
Kayıt kapalıyken yapılan denemeler yalnızca o anki geri bildirim ve takip sorusu için saklanır.
Kayıt tamamen saklı denemelerden hesaplanır; örnek ya da sabit veri yoktur.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Chunk, PracticeAttempt, PracticeQuestion, User
from app.practice.service import citation
from app.schemas.learning import AttemptSummary, ConceptProgress, LearningRecord
from app.schemas.practice import PracticeType

# Kayıtta gösterilen en fazla deneme (en yeniler).
MAX_ATTEMPTS = 200
# Konusu bilinmeyen soruların kavram adı.
UNKNOWN_CONCEPT = "Genel"


def concept_key(text: str) -> str:
    """Aynı kavramın yazım farklarını birleştirir (büyük/küçük harf, boşluk, sondaki nokta)."""
    return re.sub(r"\s+", " ", text).strip(" .").casefold()


def question_concept(question: PracticeQuestion) -> str:
    if question.rubric is not None and question.rubric.concept.strip():
        return question.rubric.concept.strip()
    return (question.topic or "").strip() or UNKNOWN_CONCEPT


def get_learning_record(db: Session, user: User, course_id: int) -> LearningRecord:
    attempts = db.scalars(
        select(PracticeAttempt)
        .join(PracticeQuestion, PracticeAttempt.question_id == PracticeQuestion.id)
        .where(
            PracticeAttempt.user_id == user.id,
            PracticeAttempt.research_logged.is_(True),
            PracticeQuestion.course_id == course_id,
        )
        .options(
            joinedload(PracticeAttempt.question).joinedload(PracticeQuestion.rubric),
            joinedload(PracticeAttempt.question)
            .joinedload(PracticeQuestion.chunk)
            .joinedload(Chunk.document),
        )
        .order_by(PracticeAttempt.created_at.desc(), PracticeAttempt.id.desc())
        .limit(MAX_ATTEMPTS)
    ).all()

    summaries: list[AttemptSummary] = []
    # Kavram → denemeleri (en yeniden eskiye; sorgu sırası korunur).
    by_concept: dict[str, list[PracticeAttempt]] = {}
    names: dict[str, str] = {}
    for attempt in attempts:
        question = attempt.question
        concept = question_concept(question)
        summaries.append(
            AttemptSummary(
                item_id=question.id,
                attempt_id=attempt.id,
                type=PracticeType(question.type),
                concept=concept,
                score=attempt.score,
                max_score=attempt.max_score,
                missing_concepts=list((attempt.feedback or {}).get("missing_concepts") or []),
                attempted_at=attempt.created_at,
                withdrawn=question.status == "withdrawn",
            )
        )
        key = concept_key(concept)
        by_concept.setdefault(key, []).append(attempt)
        names.setdefault(key, concept)

    concepts = [_progress(names[key], items) for key, items in by_concept.items()]
    # Önce hâlâ eksiği olanlar; her grupta son puanı düşük olan önde.
    concepts.sort(key=lambda c: (not c.open_gaps, c.last_score_ratio))
    return LearningRecord(
        course_id=course_id,
        logging_enabled=user.research_logging,
        attempts=summaries,
        concepts=concepts,
    )


def _ratio(attempt: PracticeAttempt) -> float:
    return attempt.score / attempt.max_score if attempt.max_score > 0 else 0.0


def _progress(concept: str, attempts: list[PracticeAttempt]) -> ConceptProgress:
    latest = attempts[0]
    return ConceptProgress(
        concept=concept,
        attempts=len(attempts),
        last_score_ratio=round(_ratio(latest), 3),
        best_score_ratio=round(max(_ratio(a) for a in attempts), 3),
        open_gaps=list((latest.feedback or {}).get("missing_concepts") or []),
        source=citation(latest.question.chunk),
    )
