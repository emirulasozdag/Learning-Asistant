"""Sınıfın sık hataları (FR-16, #20): saklı pratik denemelerinden, toplu ve anonim.

ADR-4: yalnızca derste öğrenci olan, araştırma kaydı şu an açık ve deneme anında da açık olan
(`research_logged`) kullanıcıların denemeleri sayılır. Kişi bazlı gösterim yoktur; en az
`MIN_GROUP` farklı öğrencide görülmeyen hata listelenmez (tek kişiye bağlanamasın).

Hata kaynağı değerlendiricinin `missing_concepts` çıktısıdır: çoktan seçmelide yanlış şık
sorunun kavramını eksik sayar (`wrong_option`), açık uçlu cevapta her eksik kavram ayrı
sayılır (`missing_concept`).
"""

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import Enrollment, PracticeAttempt, PracticeQuestion, User
from app.instructor.activity import MIN_GROUP
from app.learning.record import concept_key
from app.schemas.instructor import MistakeSummary
from app.schemas.practice import PracticeType

# Listelenen en fazla hata ve hata başına önerilen kaynak sayısı.
MAX_MISTAKES = 20
MAX_SOURCES = 3


@dataclass
class _Group:
    concept: str
    error_type: str
    count: int = 0
    students: set[int] = field(default_factory=set)
    sources: Counter[str] = field(default_factory=Counter)


def frequent_mistakes(db: Session, course_id: int) -> list[MistakeSummary]:
    attempts = db.scalars(
        select(PracticeAttempt)
        .join(PracticeQuestion, PracticeAttempt.question_id == PracticeQuestion.id)
        .join(User, User.id == PracticeAttempt.user_id)
        .join(
            Enrollment,
            (Enrollment.user_id == User.id) & (Enrollment.course_id == PracticeQuestion.course_id),
        )
        .where(
            PracticeQuestion.course_id == course_id,
            PracticeAttempt.research_logged.is_(True),
            User.research_logging.is_(True),
            Enrollment.role == "student",
        )
        .options(joinedload(PracticeAttempt.question).joinedload(PracticeQuestion.rubric))
    ).all()

    groups: dict[tuple[str, str], _Group] = {}
    for attempt in attempts:
        question = attempt.question
        error_type = "wrong_option" if question.type == PracticeType.MCQ else "missing_concept"
        sources = (question.rubric.source_ids if question.rubric else None) or [
            str(question.chunk_id)
        ]
        missing = (attempt.feedback or {}).get("missing_concepts") or []
        # Aynı denemede aynı kavram iki kez yazılmışsa bir kez sayılır.
        seen: set[str] = set()
        for concept in missing:
            if not isinstance(concept, str) or not (key := concept_key(concept)) or key in seen:
                continue
            seen.add(key)
            group = groups.setdefault(
                (key, error_type), _Group(concept=concept.strip(), error_type=error_type)
            )
            group.count += 1
            group.students.add(attempt.user_id)
            group.sources.update(str(source) for source in sources)

    shown = [g for g in groups.values() if len(g.students) >= MIN_GROUP]
    shown.sort(key=lambda g: (-len(g.students), -g.count, g.concept))
    return [
        MistakeSummary(
            concept=g.concept,
            error_type=g.error_type,  # type: ignore[arg-type]
            count=g.count,
            students=len(g.students),
            fixing_source_ids=[s for s, _ in g.sources.most_common(MAX_SOURCES)],
        )
        for g in shown[:MAX_MISTAKES]
    ]
