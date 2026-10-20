"""LLM ile yeniden sıralama: puana göre seçer, hata ya da eksik çıktıda aramanın sırasına döner."""

from pydantic import BaseModel

from app.llm.base import LLMError
from app.retrieval.rerank import PassageScore, RerankOutput, rerank
from app.retrieval.types import RetrievedPassage

PASSAGES = [
    RetrievedPassage(
        source_id=str(i), document_id=1, document_title="D", text=f"parca {i}", score=1
    )
    for i in range(1, 6)
]


class Scorer:
    model = "fake-reranker"

    def __init__(self, answer: BaseModel | Exception) -> None:
        self.answer = answer
        self.prompts: list[str] = []

    def complete_json(self, system, prompt, schema):
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def scores(**values: int) -> RerankOutput:
    return RerankOutput(scores=[PassageScore(label=k, relevance=v) for k, v in values.items()])


def ids(passages: list[RetrievedPassage]) -> list[str]:
    return [p.source_id for p in passages]


def test_best_scored_passages_come_first_and_irrelevant_ones_are_dropped() -> None:
    scorer = Scorer(scores(P1=1, P2=0, P3=3, P4=2, P5=3))

    chosen = rerank("soru", PASSAGES, scorer, keep=3)

    assert ids(chosen) == ["3", "5", "4"]  # eşit puanda aramanın sırası korunur
    assert "Soru: soru" in scorer.prompts[0] and "P5" in scorer.prompts[0]


def test_failure_or_incomplete_output_falls_back_to_search_order() -> None:
    assert ids(rerank("soru", PASSAGES, Scorer(LLMError("kota")), keep=2)) == ["1", "2"]
    assert ids(rerank("soru", PASSAGES, Scorer(scores(P4=3)), keep=2)) == ["1", "2"]


def test_all_zero_scores_keep_the_search_order() -> None:
    scorer = Scorer(scores(P1=0, P2=0, P3=0, P4=0, P5=0))

    assert ids(rerank("soru", PASSAGES, scorer, keep=2)) == ["1", "2"]
