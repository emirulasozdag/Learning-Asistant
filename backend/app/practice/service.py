"""Pratik döngüsü: kaynak parça → soru üret → kontrol et → sakla; cevap → değerlendir → kaydet.

Her üretilen aday (geçen ya da geçmeyen) kontrol sonuçlarıyla saklanır; kabul oranı böylece
ölçülür. Öğrenciye yalnızca bütün kontrollerden geçen soru gösterilir; hiçbiri geçmezse
`NoValidItem` (API: 422 `no_valid_item`). Anahtar ve referans cevap cevaptan önce dönmez.
"""

import logging
import re
from collections.abc import Generator
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Chunk,
    Course,
    Document,
    PracticeAttempt,
    PracticeQuestion,
    PracticeRubric,
    User,
)
from app.embeddings.base import Embedder
from app.generation.grade import Grade, GradingError, grade_choice, grade_open_answer
from app.generation.question import LANGUAGE_NAMES, GeneratedQuestion, Language, generate_question
from app.llm.base import LLMClient, LLMError
from app.retrieval.hybrid import retrieve
from app.retrieval.rerank import rerank, rerank_scored
from app.retrieval.types import RetrievedPassage
from app.schemas.common import Citation
from app.schemas.evaluation import AnswerFeedback, AnswerSubmission, CriterionScore
from app.schemas.materials import MaterialType
from app.schemas.practice import Difficulty, PracticeItem, PracticeType
from app.verification.practice_checks import (
    CheckResult,
    failures,
    independent_solve,
    passed,
    static_checks,
)

logger = logging.getLogger(__name__)

# Bir istekte en fazla bu kadar aday üretilir (her biri kontrol edilir).
MAX_CANDIDATES = 3
# Soru üretmeye yetecek en kısa parça (başlık, içindekiler gibi parçalar elenir).
MIN_PASSAGE_CHARS = 250
# Not verilen ödevler (ve çözümleri) pratik kaynağı olmaz: çözüm sızmasın. Pratik problemleri ve
# yayımlanmış eski sınavlar kullanılır (aktif sınavlar zaten yüklenmez, ADR-3).
EXCLUDED_TYPES = {MaterialType.ASSIGNMENT.value}


class NoValidItem(Exception):
    """Kontrollerden geçen bir soru üretilemedi; `reason` öğrenciye gösterilebilir."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidSubmission(ValueError):
    """Cevap türü soruyla uyuşmuyor (MCQ'ya metin, açık uçluya şık gibi)."""


@dataclass
class PracticeContext:
    """Soru isteğinin nereden geldiği: konu, belirli bir parça ya da bir denemenin eksikleri."""

    topic: str | None = None
    # Konunun ders materyalinin dilindeki karşılığı (arama bununla yapılır).
    search_query: str | None = None
    source_id: str | None = None
    follow_up_of: PracticeAttempt | None = None
    # Sohbette az önce okunan cevabın kaynakları: "bu konuda beni test et" önce bunlardan sorar.
    preferred_source_ids: list[str] = field(default_factory=list)


# Arayüzde gösterilen ilerleme adımları (AI Tutor bunları durum olayı olarak akıtır).
STAGE_PASSAGE = "Konuyu anlatan bölüm seçiliyor…"
STAGE_WRITE = "Soru yazılıyor…"
STAGE_CHECK = "Soru bağımsız çözümle kontrol ediliyor…"
STAGE_RETRY = "Soru kontrolden geçmedi; yeni bir soru yazılıyor…"


def create_question(*args, **kwargs) -> PracticeQuestion:
    """`create_question_steps` ile aynı; ilerleme adımlarını yok sayar."""
    steps = create_question_steps(*args, **kwargs)
    while True:
        try:
            next(steps)
        except StopIteration as done:
            return done.value


def create_question_steps(
    db: Session,
    course: Course,
    user: User,
    question_type: PracticeType,
    difficulty: Difficulty,
    context: PracticeContext,
    generator: LLMClient | None,
    checker: LLMClient | None,
    *,
    language: Language = "tr",
    embedder: Embedder | None = None,
    reranker: LLMClient | None = None,
) -> Generator[str, None, PracticeQuestion]:
    """İlerleme adımlarını (str) verir, sonunda gösterilebilir soruyu döndürür; yoksa NoValidItem.

    `reranker` (hızlı model) parça seçiminde ve açık uçlu cevapların eşdeğerlik kontrolünde
    kullanılır; yoksa kontrolcü kullanılır.
    """
    if generator is None or checker is None:
        raise NoValidItem("Pratik sorusu üretmek için yapay zekâ şu an kullanılamıyor.")
    topic = context.topic
    if context.follow_up_of is not None:
        missing = context.follow_up_of.feedback.get("missing_concepts") or []
        topic = ", ".join(missing) or context.follow_up_of.question.topic
    yield STAGE_PASSAGE
    passages = _candidate_passages(db, course, context, topic, embedder, reranker, question_type)

    feedback: list[str] = []
    for attempt in range(MAX_CANDIDATES):
        passage = passages[attempt % len(passages)]
        yield STAGE_RETRY if attempt else STAGE_WRITE
        try:
            generated = generate_question(
                course,
                passage,
                question_type,
                difficulty,
                generator,
                topic=topic,
                language=language,
                feedback=feedback or None,
                avoid=_previous_prompts(db, user, int(passage.source_id)) or None,
            )
        except LLMError as exc:
            logger.warning("Pratik sorusu üretilemedi: %s", exc)
            continue
        results = static_checks(generated, passage, question_type)
        if passed(results):
            yield STAGE_CHECK
            results.append(
                independent_solve(generated, passage, question_type, checker, comparer=reranker)
            )
        question = _store(
            db,
            course,
            user,
            question_type,
            difficulty,
            topic,
            passage,
            generated,
            results,
            generator.model,
            context.follow_up_of,
        )
        if passed(results):
            return question
        feedback = failures(results)
        logger.info("Pratik adayı reddedildi (%d/%d): %s", attempt + 1, MAX_CANDIDATES, feedback)
    raise NoValidItem(
        "Kontrollerden geçen bir soru üretilemedi. Konuyu biraz daha belirgin yazıp tekrar dene."
    )


def _candidate_passages(
    db: Session,
    course: Course,
    context: PracticeContext,
    topic: str | None,
    embedder: Embedder | None,
    reranker: LLMClient | None = None,
    question_type: PracticeType = PracticeType.MCQ,
) -> list[RetrievedPassage]:
    if context.source_id or context.follow_up_of is not None:
        chunk = (
            context.follow_up_of.question.chunk
            if context.follow_up_of is not None
            else _approved_chunk(db, course, context.source_id or "")
        )
        if chunk is None:
            raise NoValidItem("Seçilen kaynak bu derste bulunamadı.")
        if chunk.document.material_type in EXCLUDED_TYPES:
            raise NoValidItem("Not verilen ödevlerden pratik sorusu üretilmez.")
        return [_passage(chunk)]
    if not topic:
        raise NoValidItem("Hangi konuda soru istediğini yazar mısın?")
    query = context.search_query or topic
    # Kod izleme sorusu, konunun kodunu içeren bölümden sorulur ("binary search" → ikili arama
    # kodu; ikili arama ağacı değil).
    wants_code = question_type == PracticeType.CODE_TRACING
    need = (
        f"Şu konunun kodunu ya da sözde kodunu içeren bölüm: {query}"
        if wants_code
        else f"Şu konuyu öğreten bölüm: {query}"
    )

    preferred = _usable(
        db, [c for i in context.preferred_source_ids if (c := _approved_chunk(db, course, i))]
    )
    if preferred and reranker is not None:
        # Az önce okunan cevabın kaynakları konuyu gerçekten anlatıyorsa onlardan sor
        # (arama ve geniş sıralama gerekmez; daha hızlı ve konuya bağlı).
        scored = rerank_scored(need, preferred, reranker)
        relevant = [passage for passage, score in scored if score >= 2]
        if relevant:
            return relevant[:MAX_CANDIDATES]

    retrieval = retrieve(db, course, query, k=20 if reranker else 5, embedder=embedder)
    usable = _usable_passages(db, retrieval.passages)
    if not retrieval.relevant or not usable:
        raise NoValidItem(
            "Bu konu için ders materyalinde soru üretmeye yetecek bir bölüm bulunamadı."
        )
    if wants_code and any(_has_code(p.text) for p in usable):
        usable = [p for p in usable if _has_code(p.text)]
    if reranker is not None:
        # Konuyu öğreten parça öne gelsin ("binary search" → ikili ağaç değil, ikili arama).
        usable = rerank(need, usable, reranker, MAX_CANDIDATES)
    return usable[:MAX_CANDIDATES]


_CODE_LINE = re.compile(
    r"^\s*(\d+\s+)?(def |for |while |if |return\b|class |\w+\s*=\s*\S)", re.MULTILINE
)


def _has_code(text: str) -> bool:
    """Parçada birkaç satırlık kod ya da sözde kod var mı (kod izleme sorusu için)."""
    return len(_CODE_LINE.findall(text)) >= 3


def _usable(db: Session, chunks: list[Chunk]) -> list[RetrievedPassage]:
    return _usable_passages(db, [_passage(chunk) for chunk in chunks])


def _usable_passages(db: Session, passages: list[RetrievedPassage]) -> list[RetrievedPassage]:
    """Soru üretmeye yetecek uzunlukta ve not verilen ödevlerden olmayan parçalar."""
    ids = {p.document_id for p in passages}
    types = dict(
        db.execute(select(Document.id, Document.material_type).where(Document.id.in_(ids))).all()
    )
    return [
        p
        for p in passages
        if len(p.text) >= MIN_PASSAGE_CHARS and types.get(p.document_id) not in EXCLUDED_TYPES
    ]


def _previous_prompts(db: Session, user: User, chunk_id: int, limit: int = 5) -> list[str]:
    """Öğrencinin bu parçadan daha önce aldığı (gösterilmiş) sorular, yeniden eskiye."""
    return list(
        db.scalars(
            select(PracticeQuestion.prompt)
            .where(
                PracticeQuestion.chunk_id == chunk_id,
                PracticeQuestion.requested_by == user.id,
                PracticeQuestion.status == "released",
            )
            .order_by(PracticeQuestion.id.desc())
            .limit(limit)
        )
    )


def _approved_chunk(db: Session, course: Course, source_id: str) -> Chunk | None:
    if not source_id.isdigit():
        return None
    return db.scalar(
        select(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .where(
            Chunk.id == int(source_id),
            Chunk.course_id == course.id,
            Document.approved_at.is_not(None),
        )
    )


def _passage(chunk: Chunk) -> RetrievedPassage:
    return RetrievedPassage(
        source_id=str(chunk.id),
        document_id=chunk.document_id,
        document_title=chunk.document.title,
        text=chunk.text,
        score=1.0,
        page=chunk.page,
        t_start=chunk.t_start,
        t_end=chunk.t_end,
    )


def _store(
    db: Session,
    course: Course,
    user: User,
    question_type: PracticeType,
    difficulty: Difficulty,
    topic: str | None,
    passage: RetrievedPassage,
    generated: GeneratedQuestion,
    results: list[CheckResult],
    model: str,
    follow_up_of: PracticeAttempt | None,
) -> PracticeQuestion:
    released = passed(results)
    question = PracticeQuestion(
        course_id=course.id,
        chunk_id=int(passage.source_id),
        requested_by=user.id,
        type=question_type.value,
        topic=(topic or generated.concept)[:300],
        difficulty=difficulty,
        prompt=generated.prompt.strip(),
        options=generated.options if question_type == PracticeType.MCQ else None,
        answer_key=(
            {"correct_option": generated.correct_option}
            if question_type == PracticeType.MCQ
            else {"reference_answer": generated.reference_answer}
        ),
        explanation=generated.explanation.strip(),
        status="released" if released else "rejected",
        checks=[result.as_dict() for result in results],
        generator_model=model,
        follow_up_of_attempt_id=follow_up_of.id if follow_up_of else None,
    )
    question.rubric = PracticeRubric(
        course_id=course.id,
        concept=generated.concept[:300],
        reference_answer=generated.reference_answer,
        criteria=[c.model_dump() for c in generated.criteria],
        source_ids=[passage.source_id],
        origin="generated",
    )
    db.add(question)
    db.commit()
    return question


def to_item(question: PracticeQuestion) -> PracticeItem:
    """Öğrenciye giden görünüm: anahtar, referans cevap ve açıklama yok."""
    return PracticeItem(
        id=question.id,
        course_id=question.course_id,
        type=PracticeType(question.type),
        topic=question.topic,
        difficulty=question.difficulty,  # type: ignore[arg-type]
        prompt=question.prompt,
        options=question.options,
        source=citation(question.chunk),
    )


def citation(chunk: Chunk) -> Citation:
    return Citation(
        source_id=str(chunk.id),
        document_title=chunk.document.title,
        page=chunk.page,
        t_start=chunk.t_start,
        t_end=chunk.t_end,
    )


# --- Cevap ve değerlendirme -------------------------------------------------------------------


def released_question(db: Session, question_id: int) -> PracticeQuestion | None:
    question = db.get(PracticeQuestion, question_id)
    return question if question is not None and question.status == "released" else None


def own_attempt(db: Session, attempt_id: int, user: User, course: Course) -> PracticeAttempt | None:
    attempt = db.get(PracticeAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id or attempt.question.course_id != course.id:
        return None
    return attempt


def answer_question(
    db: Session,
    question: PracticeQuestion,
    user: User,
    submission: AnswerSubmission,
    grader: LLMClient | None,
    *,
    course_name: str,
    language: Language = "tr",
) -> tuple[PracticeAttempt, AnswerFeedback]:
    """Cevabı değerlendirir ve denemeyi kaydeder. Açık uçlu cevap değerlendirilemezse
    `GradingError` (deneme kaydedilmez, öğrenci tekrar gönderebilir)."""
    rubric = question.rubric
    if question.type == PracticeType.MCQ:
        if submission.selected_option is None:
            raise InvalidSubmission("Bu soru için bir seçenek işaretlenmeli.")
        options = question.options or []
        if submission.selected_option >= len(options):
            raise InvalidSubmission("Seçenek geçerli değil.")
        grade = grade_choice(
            submission.selected_option,
            int(question.answer_key["correct_option"]),
            options,
            rubric.concept if rubric else (question.topic or ""),
            question.explanation,
        )
    else:
        if submission.answer_text is None:
            raise InvalidSubmission("Bu soru için yazılı bir cevap gerekli.")
        if rubric is None:
            raise GradingError("Bu sorunun rubriği bulunamadı.")
        grade = grade_open_answer(
            course_name=course_name,
            prompt=question.prompt,
            reference_answer=rubric.reference_answer,
            criteria=rubric.criteria,
            source_text=question.chunk.text,
            answer=submission.answer_text,
            llm=grader,
            language=LANGUAGE_NAMES[language],
        )

    attempt = PracticeAttempt(
        question_id=question.id,
        user_id=user.id,
        answer_text=submission.answer_text,
        selected_option=submission.selected_option,
        score=grade.score,
        max_score=grade.max_score,
        feedback=_feedback_record(grade),
        grader_model=grade.model,
        research_logged=user.research_logging,
    )
    db.add(attempt)
    db.commit()
    return attempt, _feedback(attempt, question, grade)


def _feedback_record(grade: Grade) -> dict:
    return {
        "understood": grade.understood,
        "missing_concepts": grade.missing_concepts,
        "explanation": grade.explanation,
        "criteria": [vars(c) for c in grade.criteria],
    }


def _feedback(attempt: PracticeAttempt, question: PracticeQuestion, grade: Grade) -> AnswerFeedback:
    mcq = question.type == PracticeType.MCQ
    return AnswerFeedback(
        attempt_id=attempt.id,
        item_id=question.id,
        score=grade.score,
        max_score=grade.max_score,
        understood=grade.understood,
        missing_concepts=grade.missing_concepts,
        explanation=grade.explanation,
        citations=[citation(question.chunk)],
        correct_option=int(question.answer_key["correct_option"]) if mcq else None,
        reference_answer=None if mcq else question.answer_key.get("reference_answer"),
        criteria=[CriterionScore(**vars(c)) for c in grade.criteria],
    )
