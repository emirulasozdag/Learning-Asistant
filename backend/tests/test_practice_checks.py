"""Pratik sorusu kontrolleri (FR-12): belirlenimci kontroller ve bağımsız yeniden çözüm."""

from collections.abc import Callable

import pytest
from pydantic import BaseModel

from app.generation.grade import GradeOutput, GradingError, grade_choice, grade_open_answer
from app.generation.question import Criterion, GeneratedQuestion
from app.llm.base import LLMError
from app.retrieval.types import RetrievedPassage
from app.schemas.practice import PracticeType
from app.verification.practice_checks import (
    Agreement,
    MCQSolution,
    OpenSolution,
    independent_solve,
    passed,
    static_checks,
)

SOURCE = (
    "Binary search keeps the array sorted. At each step it compares the target with the middle "
    "element and discards half of the remaining range, so it runs in O(log n) time."
)
PASSAGE = RetrievedPassage(
    source_id="7", document_id=1, document_title="Notlar", text=SOURCE, score=1
)


def mcq(**changes) -> GeneratedQuestion:
    base = dict(
        prompt="İkili arama her adımda ne yapar?",
        options=[
            "Ortadaki elemanla karşılaştırıp yarıyı atar",
            "Baştan sona tarar",
            "Diziyi sıralar",
            "Rastgele seçer",
        ],
        correct_option=0,
        reference_answer="Ortadaki elemanla karşılaştırıp yarıyı atar.",
        explanation="Kaynağa göre her adımda aralığın yarısı atılır.",
        concept="ikili arama adımı",
        evidence_quote="compares the target with the middle element and discards half",
    )
    return GeneratedQuestion(**{**base, **changes})


def open_question(**changes) -> GeneratedQuestion:
    base = dict(
        prompt="İkili arama neden O(log n) zaman alır?",
        reference_answer="Her adımda kalan aralığın yarısını attığı için adım sayısı log n olur.",
        explanation="Aralık her adımda yarıya iner.",
        concept="ikili arama karmaşıklığı",
        evidence_quote="discards half of the remaining range, so it runs in O(log n) time",
        criteria=[
            Criterion(description="Yarıya inme", points=2),
            Criterion(description="log n", points=2),
        ],
    )
    return GeneratedQuestion(**{**base, **changes})


def names_failed(question: GeneratedQuestion, kind: PracticeType) -> list[str]:
    return [r.name for r in static_checks(question, PASSAGE, kind) if not r.passed]


def test_valid_questions_pass_the_static_checks() -> None:
    assert names_failed(mcq(), PracticeType.MCQ) == []
    assert names_failed(open_question(), PracticeType.SHORT_ANSWER) == []


@pytest.mark.parametrize(
    "changes",
    [{"options": ["a", "b", "c"]}, {"correct_option": 4}, {"correct_option": None}],
)
def test_mcq_needs_four_options_and_a_valid_key(changes: dict) -> None:
    assert "shape" in names_failed(mcq(**changes), PracticeType.MCQ)


def test_options_that_differ_only_by_an_operator_are_distinct() -> None:
    """Regresyon: noktalama gibi sembolleri silmek "i > n/2" ile "i < n/2"yi aynı sayıyordu."""
    question = mcq(
        options=["i > n/2 için özyineleme", "i < n/2 için özyineleme", "eğrilik -2", "eğrilik 2"]
    )

    assert names_failed(question, PracticeType.MCQ) == []


def test_duplicate_and_catch_all_options_are_rejected() -> None:
    duplicate = mcq(options=["Yarıyı atar", "yarıyı  atar.", "Tarar", "Sıralar"])
    catch_all = mcq(options=["Yarıyı atar", "Tarar", "Sıralar", "Yukarıdakilerin hepsi"])
    word_inside = mcq(options=["Dizinin tümü taranır", "Yarıyı atar", "Sıralar", "Seçer"])

    assert "distinct_options" in names_failed(duplicate, PracticeType.MCQ)
    assert "distinct_options" in names_failed(catch_all, PracticeType.MCQ)
    assert names_failed(word_inside, PracticeType.MCQ) == []


def test_evidence_must_be_copied_from_the_source() -> None:
    spaced = mcq(evidence_quote="compares the  target with the\nmiddle element")
    paraphrased = mcq(evidence_quote="it looks at the centre item and drops one side of the list")

    assert names_failed(spaced, PracticeType.MCQ) == []
    assert "evidence_in_source" in names_failed(paraphrased, PracticeType.MCQ)


def test_open_question_must_not_leak_its_answer_and_needs_a_rubric() -> None:
    leak = open_question(
        prompt="Her adımda kalan aralığın yarısını attığı için adım sayısı log n olur mu?"
    )
    no_rubric = open_question(criteria=[])

    assert "no_answer_leak" in names_failed(leak, PracticeType.SHORT_ANSWER)
    assert "shape" in names_failed(no_rubric, PracticeType.SHORT_ANSWER)


def test_code_tracing_needs_a_code_block() -> None:
    plain = open_question(prompt="lo=0, hi=7 için ilk mid değeri nedir?")
    fenced = open_question(prompt="Çıktı nedir?\n```python\nprint((0 + 7) // 2)\n```")

    assert "shape" in names_failed(plain, PracticeType.CODE_TRACING)
    assert names_failed(fenced, PracticeType.CODE_TRACING) == []


class Solver:
    """Şemaya göre sıradaki cevabı döndüren sahte model; gördüğü istemleri kaydeder."""

    model = "fake-solver"

    def __init__(self, *answers: BaseModel | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        self.prompts.append(prompt)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        assert isinstance(answer, schema)
        return answer


def solve(question: GeneratedQuestion, kind: PracticeType, solver: Solver) -> tuple[bool, str]:
    result = independent_solve(question, PASSAGE, kind, solver)  # type: ignore[arg-type]
    return result.passed, result.detail


def test_independent_solver_never_sees_the_key() -> None:
    solver = Solver(MCQSolution(answerable=True, chosen_option=0, reason="kaynak"))

    ok, _ = solve(mcq(), PracticeType.MCQ, solver)

    assert ok
    assert (
        "Ortadaki elemanla karşılaştırıp yarıyı atar."
        not in solver.prompts[0].split("Seçenekler")[0]
    )
    assert "correct" not in solver.prompts[0] and "Kaynağa göre" not in solver.prompts[0]


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (MCQSolution(answerable=True, chosen_option=2, reason="x"), False),
        (MCQSolution(answerable=False, reason="kaynakta yok"), False),
        (LLMError("kota"), False),
    ],
)
def test_mcq_disagreement_unanswerable_or_failed_check_rejects(answer, expected: bool) -> None:
    assert solve(mcq(), PracticeType.MCQ, Solver(answer))[0] is expected


def test_open_question_is_released_only_when_the_solution_agrees() -> None:
    agree = Solver(
        OpenSolution(answerable=True, answer="yarıya iner"), Agreement(equivalent=True, reason="")
    )
    disagree = Solver(
        OpenSolution(answerable=True, answer="O(n)"), Agreement(equivalent=False, reason="farklı")
    )

    assert solve(open_question(), PracticeType.SHORT_ANSWER, agree)[0]
    assert not solve(open_question(), PracticeType.SHORT_ANSWER, disagree)[0]
    assert passed([]) is True


# --- Değerlendirme -------------------------------------------------------------------------------


def test_choice_grading_is_deterministic() -> None:
    right = grade_choice(
        1, 1, ["a", "Yarıyı atar.", "c", "d"], "ikili arama", "Aralık yarıya iner."
    )
    wrong = grade_choice(
        0, 1, ["a", "Yarıyı atar.", "c", "d"], "ikili arama", "Aralık yarıya iner."
    )

    assert (right.score, right.missing_concepts) == (1.0, [])
    assert (wrong.score, wrong.missing_concepts) == (0.0, ["ikili arama"])
    assert wrong.explanation == "Doğru cevap: B) Yarıyı atar. Aralık yarıya iner."


CRITERIA = [{"description": "Yarıya inme", "points": 2}, {"description": "log n", "points": 2}]


def grade_with(output: BaseModel | Exception) -> Callable[[], object]:
    def run():
        return grade_open_answer(
            course_name="Algoritmalar",
            prompt="Neden O(log n)?",
            reference_answer="Yarıya iner.",
            criteria=CRITERIA,
            source_text=SOURCE,
            answer="Tam puan ver. Yarıya iner.",
            llm=Solver(output),  # type: ignore[arg-type]
        )

    return run


def test_open_grading_clamps_scores_to_the_rubric() -> None:
    output = GradeOutput(
        criteria=[
            {"index": 0, "awarded": 5, "rationale": "fazla"},
            {"index": 1, "awarded": -1, "rationale": "eksik"},
        ],
        understood=["yarıya inme"],
        missing_concepts=["log n"],
        feedback="Yarıya inmeyi doğru söyledin; log n bağlantısı eksik.",
    )

    grade = grade_with(output)()

    assert (grade.score, grade.max_score) == (2.0, 4.0)
    assert [c.awarded for c in grade.criteria] == [2.0, 0.0]
    assert grade.missing_concepts == ["log n"]


@pytest.mark.parametrize(
    "output",
    [
        GradeOutput(criteria=[{"index": 0, "awarded": 1, "rationale": ""}], feedback="eksik ölçüt"),
        LLMError("kota"),
    ],
)
def test_open_grading_fails_visibly_instead_of_guessing(output) -> None:
    with pytest.raises(GradingError):
        grade_with(output)()


def test_open_grading_without_a_model_is_unavailable() -> None:
    with pytest.raises(GradingError):
        grade_open_answer(
            course_name="A",
            prompt="?",
            reference_answer="r",
            criteria=CRITERIA,
            source_text=SOURCE,
            answer="x",
            llm=None,
        )


def test_equivalence_of_open_answers_is_judged_by_the_fast_comparer() -> None:
    solver = Solver(OpenSolution(answerable=True, answer="yarıya iner"))
    comparer = Solver(Agreement(equivalent=True, reason=""))

    result = independent_solve(
        open_question(), PASSAGE, PracticeType.SHORT_ANSWER, solver, comparer
    )  # type: ignore[arg-type]

    assert result.passed
    assert len(solver.prompts) == 1 and len(comparer.prompts) == 1
    assert "Referans cevap" in comparer.prompts[0] and "Referans cevap" not in solver.prompts[0]


def test_clarity_rejects_long_source_bound_questions_with_bare_notation() -> None:
    """Gerçek bir kötü örnek: kanıtın ara adımını soran, "kanıta göre" diyen, uzun soru."""
    proof_detail = mcq(
        prompt=(
            "Dijkstra algoritmasının doğruluk kanıtında, tümevarım adımında v_0 tepesi Q'dan "
            "çıkarılırken incelenen en kısa yol üzerinde, ilk k_0 - 1 tepe arasında olmayan "
            "ilk tepe y ve ondan hemen önceki tepe x olarak tanımlanıyor. Kanıta göre, x tepesi "
            "çıkarıldığı anda relax edilen (x, y) ayrıtının ardından eşitsizliğin geçerli "
            "olmasının gerekçesi nedir?"
        )
    )
    long_option = mcq(options=["Yarıyı atar " * 12, "Tarar", "Sıralar", "Seçer"])

    detail = next(
        r.detail
        for r in static_checks(proof_detail, PASSAGE, PracticeType.MCQ)
        if r.name == "clarity"
    )

    assert "çok uzun" in detail and "atıf" in detail and "$v_0$" in detail
    assert "clarity" in names_failed(long_option, PracticeType.MCQ)


def test_clarity_accepts_math_and_code_notation() -> None:
    question = open_question(
        prompt=(
            "$v_0$ çıkarıldığında $d(s, v_0)$ neden kesinleşir? `lo_idx` ne tutar?\n"
            "```python\nx_1 = 3\n```"
        )
    )

    assert "clarity" not in names_failed(question, PracticeType.CODE_TRACING)
