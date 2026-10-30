"""Dört karşılaştırma koşulu (ANALYSIS §9, #18).

Aynı sorular, aynı üretici model ve aynı indeksle koşulur; koşullar yalnızca hattın şu
parçalarında ayrılır (`SETTINGS`, koşu kaydına yazılır):

| Koşul | Arama | Kapı | Alıntı doğrulama / iddia kontrolü | Oynatma konumu |
|---|---|---|---|---|
| no_rag | yok | yok | yok (alıntısız) | yok |
| basic_rag | yalnız anlamsal, ilk 5 | yok | yok (etiketler yalnızca kaynağa çevrilir) | yok |
| full | hibrit + RRF | var | var (ürün hattı, `/ask`) | yok |
| full_video_time | hibrit + RRF + video komşuları | var | var | gold sorudaki `playback` |

no_rag ve basic_rag temel çizgidir: ürün davranışı değil, karşılaştırma için minimal hatlar.
Bu modül veritabanına dokunmaz; arama ve model çağrısı çağırandan gelir (`run._backend_ask`).
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


class Condition(StrEnum):
    """150 test sorusunun koşulduğu 4 karşılaştırma koşulu."""

    NO_RAG = "no_rag"
    BASIC_RAG = "basic_rag"
    FULL = "full"
    FULL_VIDEO_TIME = "full_video_time"


SETTINGS: dict[Condition, dict[str, str | bool | int]] = {
    Condition.NO_RAG: {
        "retrieval": "none",
        "relevance_gate": False,
        "citation_verification": False,
        "playback_position": False,
    },
    Condition.BASIC_RAG: {
        "retrieval": "dense",
        "k": 5,
        "relevance_gate": False,
        "citation_verification": False,
        "playback_position": False,
    },
    Condition.FULL: {
        "retrieval": "hybrid",
        "k": 5,
        "relevance_gate": True,
        "citation_verification": True,
        "playback_position": False,
    },
    Condition.FULL_VIDEO_TIME: {
        "retrieval": "hybrid+video",
        "k": 5,
        "relevance_gate": True,
        "citation_verification": True,
        "playback_position": True,
    },
}

BASIC_K = 5

CLOSED_BOOK_PROMPT = """\
You are a study assistant for the course "{course_name}". Answer the student's question from \
your own knowledge, briefly and in the language of the question. If you do not know the answer, \
say so in one sentence.\
"""

BASIC_RAG_PROMPT = """\
You are a study assistant for the course "{course_name}". Answer the student's question using \
the course excerpts in <sources>. After each sentence, cite the excerpt it relies on as [S1], \
[S2]. Answer briefly and in the language of the question.\
"""

_LABEL = re.compile(r"\[(S\d+)\]")


class TextModel(Protocol):
    """`app.llm.base.LLMClient`'ın bu modülün kullandığı kısmı."""

    model: str

    def stream_text(self, system: str, messages: list) -> Iterable[str]: ...


@dataclass
class Passage:
    source_id: str
    text: str


@dataclass
class ConditionAnswer:
    outcome: str
    text: str | None
    model: str | None
    cited_source_ids: list[str] = field(default_factory=list)
    retrieved: list[Passage] = field(default_factory=list)


def closed_book(question: str, course_name: str, llm: TextModel | None) -> ConditionAnswer:
    """no_rag: yalnızca soru; arama yok, alıntı yok."""
    if llm is None:
        raise RuntimeError("no_rag koşulu LLM olmadan koşulamaz (LLM_API_KEY)")
    system = CLOSED_BOOK_PROMPT.format(course_name=course_name)
    return _generate(llm, system, question, retrieved=[])


def basic_rag(
    question: str, course_name: str, passages: Sequence[Passage], llm: TextModel | None
) -> ConditionAnswer:
    """basic_rag: anlamsal aramanın ilk 5 parçası, kapı ve doğrulama yok."""
    if llm is None:
        raise RuntimeError("basic_rag koşulu LLM olmadan koşulamaz (LLM_API_KEY)")
    labels = {f"S{index}": p for index, p in enumerate(passages[:BASIC_K], start=1)}
    sources = "\n".join(
        f'<source label="{label}">\n{p.text}\n</source>' for label, p in labels.items()
    )
    prompt = f"<sources>\n{sources}\n</sources>\n\nQuestion: {question}"
    system = BASIC_RAG_PROMPT.format(course_name=course_name)
    answer = _generate(llm, system, prompt, retrieved=list(labels.values()))
    if answer.text:
        cited: list[str] = []
        for label in _LABEL.findall(answer.text):
            passage = labels.get(label)
            if passage is not None and passage.source_id not in cited:
                cited.append(passage.source_id)
        answer.cited_source_ids = cited
    return answer


def _generate(
    llm: TextModel, system: str, prompt: str, retrieved: list[Passage]
) -> ConditionAnswer:
    from app.llm.base import LLMError, LLMRefusal

    try:
        text = "".join(llm.stream_text(system, [{"role": "user", "content": prompt}]))
    except LLMRefusal:
        return ConditionAnswer("model_refusal", None, llm.model, retrieved=retrieved)
    except LLMError:
        return ConditionAnswer("provider_failure", None, llm.model, retrieved=retrieved)
    return ConditionAnswer("answered", text.strip(), llm.model, retrieved=retrieved)
