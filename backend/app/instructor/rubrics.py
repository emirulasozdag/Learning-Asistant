"""Eğitmenin rubrik ve referans cevap girişi (#15, FR-13).

- Soruya bağlı giriş, sorunun üretilmiş rubriğinin yerine geçer: `origin="instructor"`, onaylı
  (giren ve zaman yazılır). Açık uçlu cevaplar bundan sonra bu referans ve kriterlerle
  değerlendirilir; öğrenciye cevaptan sonra gösterilen referans cevap da budur. Sorunun
  `answer_key`'i üreticinin çıktısı olarak değişmeden kalır; rubriğin önceki hâli (üretilen ilk
  hâl ya da eğitmenin önceki düzeltmesi) `practice_rubric_revisions`'a yazılır.
- Kavrama bağlı giriş (`practice_item_id` yok) dersin rubriği olarak saklanır.
- Rubrik girmek sorunun durumunu değiştirmez: geri çekilmiş soru, eğitmen onaylayana
  (`POST /instructor/reviews`) kadar öğrenciye sunulmaz.
"""

from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.errors import ApiError
from app.auth.dependencies import not_found_error
from app.db.models import (
    Chunk,
    Document,
    PracticeQuestion,
    PracticeRubric,
    PracticeRubricRevision,
    User,
)
from app.instructor.review import REVIEWABLE_STATUSES
from app.schemas.practice import PracticeType
from app.schemas.rubrics import Rubric, RubricIn
from app.sources.lookup import chunk_id

# Eğitmenin listesinde gösterilen en fazla rubrik (en yeniler).
MAX_RUBRICS = 100


def create_rubric(db: Session, course_id: int, reviewer: User, rubric_in: RubricIn) -> Rubric:
    """Rubriği ve referans cevabı kaydet; soruya bağlıysa sorunun rubriğinin yerine geçer."""
    source_ids = _course_source_ids(db, course_id, rubric_in.source_ids)
    criteria = [criterion.model_dump() for criterion in rubric_in.criteria]
    now = datetime.now(UTC)

    if rubric_in.practice_item_id is None:
        rubric = PracticeRubric(course_id=course_id)
        db.add(rubric)
    else:
        question = db.get(PracticeQuestion, rubric_in.practice_item_id)
        if (
            question is None
            or question.course_id != course_id
            or question.status not in REVIEWABLE_STATUSES
        ):
            raise not_found_error("practice_item_not_found")
        if question.type == PracticeType.MCQ:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Çoktan seçmeli sorular cevap anahtarıyla değerlendirilir; rubrik açık uçlu "
                "sorulara girilir.",
                "validation_error",
            )
        rubric = question.rubric
        if rubric is None:
            rubric = PracticeRubric(course_id=course_id)
            question.rubric = rubric
        else:
            db.add(_revision_of(rubric, reviewer))
        source_ids = source_ids or [str(question.chunk_id)]

    rubric.concept = rubric_in.concept
    rubric.reference_answer = rubric_in.reference_answer
    rubric.criteria = criteria
    rubric.source_ids = source_ids
    rubric.origin = "instructor"
    rubric.approved = True
    rubric.approved_by = reviewer.id
    rubric.approved_at = now
    db.commit()
    return to_rubric(rubric)


def list_rubrics(db: Session, course_id: int) -> list[Rubric]:
    """Dersin rubrikleri: kavram rubrikleri ve öğrenciye sunulmuş (ya da geri çekilmiş) soruların
    rubrikleri. Otomatik kontrolün reddettiği sorular öğrenciye hiç gitmediği için listede yok."""
    rubrics = db.scalars(
        select(PracticeRubric)
        .outerjoin(PracticeQuestion, PracticeQuestion.id == PracticeRubric.question_id)
        .where(
            PracticeRubric.course_id == course_id,
            or_(
                PracticeRubric.question_id.is_(None),
                PracticeQuestion.status.in_(REVIEWABLE_STATUSES),
            ),
        )
        # Son değişen önce: eğitmenin güncellediği üretilmiş rubrik de başa gelir.
        .order_by(
            func.coalesce(PracticeRubric.approved_at, PracticeRubric.created_at).desc(),
            PracticeRubric.id.desc(),
        )
        .limit(MAX_RUBRICS)
    ).all()
    return [to_rubric(rubric) for rubric in rubrics]


def _revision_of(rubric: PracticeRubric, reviewer: User) -> PracticeRubricRevision:
    """Değiştirilmeden önceki içerik (üretilen ilk hâl ya da eğitmenin önceki düzeltmesi)."""
    return PracticeRubricRevision(
        rubric_id=rubric.id,
        concept=rubric.concept,
        reference_answer=rubric.reference_answer,
        criteria=rubric.criteria,
        source_ids=rubric.source_ids,
        origin=rubric.origin,
        approved=rubric.approved,
        replaced_by=reviewer.id,
    )


def to_rubric(rubric: PracticeRubric) -> Rubric:
    return Rubric(
        id=rubric.id,
        course_id=rubric.course_id,
        concept=rubric.concept,
        reference_answer=rubric.reference_answer,
        criteria=rubric.criteria,
        practice_item_id=rubric.question_id,
        source_ids=rubric.source_ids,
        origin=rubric.origin,  # type: ignore[arg-type]
        approved=rubric.approved,
    )


def _course_source_ids(db: Session, course_id: int, source_ids: list[str]) -> list[str]:
    """Kaynaklar bu dersin onaylı, hazır materyalinden olmalı; değilse 422 (varlık sızdırılmaz).
    Kimlikler tekilleştirilir ve olağan biçimde ("012" → "12") saklanır."""
    parsed = [chunk_id(source_id) for source_id in source_ids]
    if any(value is None for value in parsed):
        raise _unknown_sources()
    unique = list(dict.fromkeys(value for value in parsed if value is not None))
    if not unique:
        return []
    found = set(
        db.scalars(
            select(Chunk.id)
            .join(Document, Document.id == Chunk.document_id)
            .where(
                Chunk.id.in_(unique),
                Document.course_id == course_id,
                Document.approved_at.is_not(None),
                Document.status == "ready",
            )
        ).all()
    )
    if len(found) != len(unique):
        raise _unknown_sources()
    return [str(value) for value in unique]


def _unknown_sources() -> ApiError:
    return ApiError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "Kaynaklardan biri bu dersin materyalinde bulunamadı.",
        "source_not_found",
    )
