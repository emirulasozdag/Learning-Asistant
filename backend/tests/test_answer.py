"""Cite-or-decline cevap üretimi ve alıntı doğrulama — sahte LLM ile (anahtar gerekmez)."""

from collections.abc import Iterator

from pydantic import BaseModel

from app.db.models import Course
from app.generation.answer import NOT_COVERED, REFUSED, UNSUPPORTED, stream_answer
from app.llm.base import ChatMessage, LLMError, LLMRefusal
from app.retrieval.types import RetrievalResult, RetrievedPassage
from app.schemas.ask import AskResponse
from app.verification.citations import MIN_COVERAGE, resolve_citations, verify_answer

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
    assert response.outcome == "insufficient_evidence"
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
    assert response.outcome == "answered" and response.unsupported_removed == 0
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
    assert response.outcome == "insufficient_evidence"
    assert [c.source_id for c in response.suggested_sources] == ["11", "12"]


def test_answer_starting_with_y_is_not_mistaken_for_decline() -> None:
    llm = FakeLLM(["Y", "arı elenir [S1]."])

    deltas, response = run(llm)

    assert "".join(deltas) == "Yarı elenir [S1]."
    assert response.answer == "Yarı elenir [1]."


def test_invalid_citation_removes_its_claim_not_only_the_marker() -> None:
    llm = FakeLLM(["Sag yari elenir [S1]. Arama O(log n) surer [S2]. Uydurma bir iddia [S9]."])

    _, response = run(llm)

    assert response.outcome == "answered"
    assert response.answer == "Sag yari elenir [1]. Arama O(log n) surer [2]."
    assert "Uydurma" not in response.answer
    assert response.unsupported_removed == 1


def test_answer_mostly_backed_by_invented_citations_is_rejected() -> None:
    _, response = run(FakeLLM(["Dogru bir iddia [S2]. Uydurma bir iddia [S9]."]))

    assert response.declined and response.outcome == "unsupported"
    assert response.decline_reason == UNSUPPORTED
    assert response.answer is None


def test_uncited_trailing_claim_is_removed() -> None:
    llm = FakeLLM(["Sag yari elenir [S1]. Arama O(log n) surer [S2]. Ayrica cok hizlidir."])

    _, response = run(llm)

    assert response.answer == "Sag yari elenir [1]. Arama O(log n) surer [2]."
    assert response.unsupported_removed == 1


def test_answer_without_any_citation_is_rejected() -> None:
    _, response = run(FakeLLM(["Ikili arama her adimda yariya boler."]))

    assert response.declined and response.outcome == "unsupported"


def test_answer_without_any_valid_citation_is_declined() -> None:
    _, response = run(FakeLLM(["Kaynaksiz bir iddia [S7]."]))

    assert response.declined and response.decline_reason == UNSUPPORTED
    assert response.outcome == "unsupported"
    assert response.answer is None


def test_partial_answer_keeps_the_cited_part_and_reports_the_gap() -> None:
    llm = FakeLLM(
        ["Dizi sirali oldugu icin sag yari elenir [S1].\n\n", "EKSİK: Karmasikligin ispati yok."]
    )

    _, response = run(llm)

    assert response.outcome == "answered"
    assert response.answer == "Dizi sirali oldugu icin sag yari elenir [1]."
    assert response.coverage_gap == "Karmasikligin ispati yok."


def test_only_a_gap_line_means_the_material_does_not_cover_it() -> None:
    _, response = run(FakeLLM(["EKSİK: Materyalde bu konu yok."]))

    assert response.declined and response.outcome == "insufficient_evidence"
    assert response.decline_reason == "Materyalde bu konu yok."


def test_refusal_is_reported_as_decline() -> None:
    _, response = run(FakeLLM(error=LLMRefusal("x")))

    assert response.declined and response.decline_reason == REFUSED
    assert response.outcome == "model_refusal"


def test_llm_error_mid_stream_replaces_draft_with_marked_excerpt() -> None:
    deltas, response = run(FakeLLM(["Sag yari "], error=LLMError("ag koptu")))

    # Taslak akmıştı; son cevap onun yerine geçer ve servis hatası olarak işaretlenir.
    assert deltas == ["Sag yari "]
    assert response.outcome == "provider_failure"
    assert response.mode == "extractive" and not response.declined
    assert "Sag yari elenir." in response.answer
    assert [c.source_id for c in response.citations] == ["11"]


def test_llm_error_before_any_text_is_provider_failure() -> None:
    deltas, response = run(FakeLLM(error=LLMError("anahtar gecersiz")))

    assert deltas == []
    assert response.outcome == "provider_failure"


def test_without_llm_best_passage_is_quoted_with_its_source() -> None:
    _, response = run(None)

    assert response.mode == "extractive" and response.outcome == "answered"
    assert response.answer.endswith("Sag yari elenir. [1]")
    assert [c.page for c in response.citations] == [2]
    assert [c.source_id for c in response.suggested_sources] == ["12"]


def test_resolve_citations_orders_by_first_appearance_and_deduplicates() -> None:
    labels = {"S1": PASSAGES[0], "S2": PASSAGES[1]}

    text, cited = resolve_citations("B [S2]. A [S1]. B tekrar [S2].", labels)

    assert text == "B [1]. A [2]. B tekrar [1]."
    assert [p.source_id for p in cited] == ["12", "11"]


LABELS = {"S1": PASSAGES[0], "S2": PASSAGES[1]}


def test_uncited_sentences_share_the_following_citation_in_their_paragraph() -> None:
    answer = "Dizi sirali tutulur. Ortadaki elemana bakilir. Sag yari elenir [S1]."

    result = verify_answer(answer, LABELS)

    assert result.text == "Dizi sirali tutulur. Ortadaki elemana bakilir. Sag yari elenir [1]."
    assert result.supported_claims == 3 and result.dropped_claims == []


def test_invented_citation_also_drops_the_sentences_it_was_covering() -> None:
    result = verify_answer(
        "Sag yari elenir [S1]. Bu bir uydurma. Ve devami da uydurma [S9]. "
        "Arama O(log n) surer [S2].",
        LABELS,
    )

    assert result.text == "Sag yari elenir [1]. Arama O(log n) surer [2]."
    assert result.dropped_claims == ["Bu bir uydurma.", "Ve devami da uydurma [S9]."]
    assert result.invalid_labels == ["S9"]
    assert result.coverage == 0.5 and not result.accepted


def test_valid_label_next_to_invented_one_is_repaired() -> None:
    result = verify_answer("Sag yari elenir [S1][S9]. Arama O(log n) surer [S2] [S8].", LABELS)

    assert result.text == "Sag yari elenir [1]. Arama O(log n) surer [2]."
    assert result.invalid_labels == ["S8", "S9"]
    assert result.dropped_claims == [] and result.accepted


def test_several_labels_in_one_bracket_count_as_citations() -> None:
    """Gemini "[S1, S2]" yazıyor; açılmazsa doğru cevaplar "doğrulanamadı" diye reddediliyordu."""
    result = verify_answer(
        "Sag yari elenir [S1, S2]. Arama O(log n) surer [S2; S9]. Dizi siralidir [S1 ,S2].", LABELS
    )

    assert result.text == "Sag yari elenir [1][2]. Arama O(log n) surer [2]. Dizi siralidir [1][2]."
    assert result.invalid_labels == ["S9"]
    assert result.dropped_claims == [] and result.accepted


def test_citation_after_the_period_belongs_to_that_sentence() -> None:
    result = verify_answer("Sag yari elenir. [S1] Arama O(log n) surer. [S2]", LABELS)

    assert result.text == "Sag yari elenir. [1] Arama O(log n) surer. [2]"
    assert result.dropped_claims == []


def test_list_items_are_checked_one_by_one() -> None:
    answer = (
        "Adimlar sunlardir:\n"
        "1. Ortadaki elemana bakilir [S1].\n"
        "2. Uydurma bir adim eklenir.\n"
        "3. Sag yari elenir [S1].\n"
        "4. Toplam sure O(log n) olur [S2]."
    )

    result = verify_answer(answer, LABELS)

    assert result.text == (
        "Adimlar sunlardir:\n"
        "1. Ortadaki elemana bakilir [1].\n"
        "3. Sag yari elenir [1].\n"
        "4. Toplam sure O(log n) olur [2]."
    )
    assert result.coverage == 0.75 and result.accepted


def test_code_blocks_and_headings_are_kept_verbatim() -> None:
    answer = (
        "## Ikili arama\n\n"
        "Kaynaktaki kod:\n\n"
        "```python\n"
        "def ara(a, x):\n"
        "    orta  = len(a) // 2\n"
        "    return orta\n"
        "```\n\n"
        "Bu fonksiyon ortadaki indeksi bulur [S1]."
    )

    result = verify_answer(answer, LABELS)

    assert result.text == answer.replace("[S1]", "[1]")
    assert result.supported_claims == 1 and result.dropped_claims == []


def test_paragraph_left_empty_is_removed_with_its_blank_lines() -> None:
    answer = (
        "Sag yari elenir [S1].\n\n"
        "Tamamen kaynaksiz bir paragraf burada.\n\n"
        "Arama O(log n) surer [S2]."
    )

    result = verify_answer(answer, LABELS)

    assert result.text == "Sag yari elenir [1].\n\nArama O(log n) surer [2]."
    assert result.coverage >= MIN_COVERAGE


def test_short_fragments_and_introductions_are_not_claims() -> None:
    result = verify_answer("Evet. Kisaca anlatayim:\n\nSag yari elenir [S1].", LABELS)

    assert result.text == "Evet. Kisaca anlatayim:\n\nSag yari elenir [1]."
    assert result.supported_claims == 1 and result.dropped_claims == []
