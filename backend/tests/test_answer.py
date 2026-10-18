"""Cite-or-decline cevap üretimi ve alıntı doğrulama — sahte LLM ile (anahtar gerekmez)."""

from collections.abc import Iterator

from pydantic import BaseModel

from app.db.models import Course
from app.generation.answer import NOT_COVERED, REFUSED, UNSUPPORTED, stream_answer
from app.llm.base import ChatMessage, LLMError, LLMRefusal
from app.retrieval.types import RetrievalResult, RetrievedPassage
from app.schemas.ask import AskResponse
from app.verification.citations import resolve_citations

COURSE = Course(id=1, code="BLM2512", name="Veri Yapilari", language="tr")


def passage(source_id: str, text: str = "metin", page: int = 1) -> RetrievedPassage:
    return RetrievedPassage(
        source_id=source_id, document_id=1, document_title="Notlar", text=text, score=1.0, page=page
    )


PASSAGES = [passage("11", "Sag yari elenir.", page=2), passage("12", "O(log n).", page=4)]
RELEVANT = RetrievalResult(passages=PASSAGES, relevant=True, best_similarity=0.85)


class FakeLLM:
    """Cevabı verilen parçalar halinde akıtan ya da hata fırlatan sahte LLM."""

    name = "fake"
    model = "fake-model"

    def __init__(self, chunks: list[str] | None = None, error: Exception | None = None) -> None:
        self.chunks = chunks or []
        self.error = error
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def stream_text(self, system: str, messages: list[ChatMessage]) -> Iterator[str]:
        self.calls.append((system, messages))
        yield from self.chunks
        if self.error:
            raise self.error

    def complete_json[T: BaseModel](self, system: str, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError


def run(
    llm: FakeLLM | None,
    retrieval: RetrievalResult = RELEVANT,
    history: list[ChatMessage] | None = None,
) -> tuple[list[str], AskResponse]:
    items = list(stream_answer(COURSE, "Neden?", history or [], retrieval, llm))
    *deltas, final = items
    assert isinstance(final, AskResponse)
    assert all(isinstance(d, str) for d in deltas)
    return deltas, final


def test_irrelevant_question_is_declined_without_calling_llm() -> None:
    llm = FakeLLM(["x"])

    deltas, response = run(llm, RetrievalResult(passages=PASSAGES, relevant=False))

    assert response.declined and response.decline_reason == NOT_COVERED
    assert response.suggested_sources == []
    assert deltas == [] and llm.calls == []


def test_no_passages_declines_without_calling_llm() -> None:
    llm = FakeLLM(["x"])

    _, response = run(llm, RetrievalResult(passages=[], relevant=True))

    assert response.declined and llm.calls == []


def test_streamed_answer_is_validated_and_renumbered() -> None:
    llm = FakeLLM(["Sag yari ", "elenir [S1]. Karmasiklik ", "O(log n) [S2]."])

    deltas, response = run(llm)

    assert "".join(deltas) == "Sag yari elenir [S1]. Karmasiklik O(log n) [S2]."
    assert not response.declined and response.mode == "llm"
    assert response.answer == "Sag yari elenir [1]. Karmasiklik O(log n) [2]."
    assert [(c.source_id, c.page) for c in response.citations] == [("11", 2), ("12", 4)]
    assert response.model == "fake-model"


def test_prompt_contains_labelled_sources_history_and_course_name() -> None:
    llm = FakeLLM(["Cevap [S1]."])
    history: list[ChatMessage] = [
        {"role": "user", "content": "Ikili arama nedir?"},
        {"role": "assistant", "content": "Sirali dizide arama."},
    ]

    run(llm, history=history)

    system, messages = llm.calls[0]
    assert "Veri Yapilari" in system and '"YOK:"' in system
    assert messages[:2] == history
    assert '<kaynak etiket="S1" doküman="Notlar" sayfa="2">' in messages[-1]["content"]
    assert messages[-1]["content"].endswith("Soru: Neden?")


def test_decline_prefix_is_not_streamed_and_becomes_decline() -> None:
    llm = FakeLLM(["Y", "OK: Materyalde ", "heap konusu yok."])

    deltas, response = run(llm)

    assert deltas == []
    assert response.declined and response.decline_reason == "Materyalde heap konusu yok."
    assert [c.source_id for c in response.suggested_sources] == ["11", "12"]


def test_answer_starting_with_y_is_not_mistaken_for_decline() -> None:
    llm = FakeLLM(["Y", "arı elenir [S1]."])

    deltas, response = run(llm)

    assert "".join(deltas) == "Yarı elenir [S1]."
    assert response.answer == "Yarı elenir [1]."


def test_unknown_citation_labels_are_dropped() -> None:
    _, response = run(FakeLLM(["Dogru [S2]. Uydurma [S9]."]))

    assert response.answer == "Dogru [1]. Uydurma ."
    assert [c.source_id for c in response.citations] == ["12"]


def test_answer_without_any_valid_citation_is_declined() -> None:
    _, response = run(FakeLLM(["Kaynaksiz bir iddia [S7]."]))

    assert response.declined and response.decline_reason == UNSUPPORTED
    assert response.answer is None


def test_refusal_is_reported_as_decline() -> None:
    _, response = run(FakeLLM(error=LLMRefusal("x")))

    assert response.declined and response.decline_reason == REFUSED


def test_llm_error_mid_stream_falls_back_to_extractive_answer() -> None:
    deltas, response = run(FakeLLM(["Sag yari "], error=LLMError("ag koptu")))

    assert deltas == ["Sag yari "]
    assert response.mode == "extractive" and not response.declined
    assert "Sag yari elenir." in response.answer
    assert [c.source_id for c in response.citations] == ["11"]


def test_without_llm_best_passage_is_quoted_with_its_source() -> None:
    _, response = run(None)

    assert response.mode == "extractive"
    assert response.answer.endswith("Sag yari elenir. [1]")
    assert [c.page for c in response.citations] == [2]
    assert [c.source_id for c in response.suggested_sources] == ["12"]


def test_resolve_citations_orders_by_first_appearance_and_deduplicates() -> None:
    labels = {"S1": PASSAGES[0], "S2": PASSAGES[1]}

    text, cited = resolve_citations("B [S2]. A [S1]. B tekrar [S2].", ["S1"], labels)

    assert text == "B [1]. A [2]. B tekrar [1]."
    assert [p.source_id for p in cited] == ["12", "11"]
