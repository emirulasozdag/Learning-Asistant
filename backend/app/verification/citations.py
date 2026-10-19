"""Alıntı doğrulama: modelin cevabındaki her iddia getirilen bir kaynağa dayanmalı.

Cevap paragraf / liste maddesi / cümle birimlerine ayrılır:
- Etiketsiz cümleler, aynı paragrafta kendilerinden sonra gelen ilk etiketli cümlenin
  kaynağını paylaşır ("A. B. C [S1]." → üçü de S1'e dayanır).
- Hiç geçerli etiketi olmayan (yalnızca uydurma [S9] taşıyan) cümle, ona bağlanan etiketsiz
  cümlelerle birlikte çıkarılır. Yalnızca etiketi silip iddiayı bırakmak yeterli değildir.
- Paragraf sonunda etiketsiz kalan cümleler alıntısız iddiadır; çıkarılır.
- Kod blokları, başlıklar, ":" ile biten giriş cümleleri ve çok kısa etiketsiz parçalar
  ("Evet.") iddia sayılmaz, olduğu gibi kalır.

Desteklenen iddiaların oranı MIN_COVERAGE altındaysa ya da geçerli alıntı kalmazsa cevap
bütünüyle reddedilmelidir (`Verification.accepted`).
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from app.retrieval.types import RetrievedPassage

_LABEL = re.compile(r"\[(S\d+)\]")
# Etiket ve önündeki tek boşluk: bilinmeyen etiket silinirken çift boşluk kalmasın.
_LABEL_WITH_SPACE = re.compile(r"( ?)\[(S\d+)\]")
_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_LIST_ITEM = re.compile(r"[ \t]*(?:[-*•]|\d+[.)])\s+")
_HEADING = re.compile(r"[ \t]*#{1,6}\s")
# Cümle sonu: nokta/soru/ünlem ve hemen ardından gelebilecek etiketler ("… elenir. [S1]").
_SENTENCE_END = re.compile(r"[.!?…]+(?:\s*\[S\d+\])*(?=\s|$)")
_WORD = re.compile(r"\w+")

# Desteklenen iddiaların en az bu oranı kalmalı; altındaysa cevap gösterilmez.
MIN_COVERAGE = 0.6
# Bundan az kelimeli etiketsiz parçalar iddia sayılmaz ("Evet.", "**Özet**").
MIN_CLAIM_WORDS = 3


@dataclass
class Verification:
    """Doğrulanmış (çıkarılan iddialar atılmış, [1], [2]... numaralı) cevap ve özeti."""

    text: str
    cited: list[RetrievedPassage]
    supported_claims: int = 0
    dropped_claims: list[str] = field(default_factory=list)
    invalid_labels: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        total = self.supported_claims + len(self.dropped_claims)
        return self.supported_claims / total if total else 0.0

    @property
    def accepted(self) -> bool:
        return bool(self.text and self.cited) and self.coverage >= MIN_COVERAGE


@dataclass
class _Sentence:
    start: int
    end: int
    labels: list[str]
    claim: bool


def verify_answer(answer: str, labels: dict[str, RetrievedPassage]) -> Verification:
    """Cevaptaki desteksiz iddiaları çıkarır, kalan etiketleri doğrulayıp numaralandırır."""
    pieces: list[str] = []
    cursor = 0
    supported = 0
    dropped: list[str] = []
    invalid: list[str] = []

    for start, end in _blocks(answer):
        # Madde işareti ("- ", "2. ") cümleye dahil edilmez; yeniden kurarken korunur.
        marker = _LIST_ITEM.match(answer, start)
        body_start = marker.end() if marker else start
        sentences = _sentences(answer, body_start, end)
        keep = [True] * len(sentences)
        pending: list[int] = []
        for index, sentence in enumerate(sentences):
            if not sentence.claim:
                continue
            if not sentence.labels:
                pending.append(index)
                continue
            group, pending = [*pending, index], []
            invalid += [label for label in sentence.labels if label not in labels]
            if any(label in labels for label in sentence.labels):
                supported += len(group)
            else:
                for member in group:
                    keep[member] = False
        for member in pending:
            keep[member] = False

        if all(keep):
            continue
        texts = [answer[sentence.start : sentence.end].strip() for sentence in sentences]
        dropped += [text for text, ok in zip(texts, keep, strict=True) if not ok]
        kept = [text for text, ok in zip(texts, keep, strict=True) if ok]
        pieces.append(answer[cursor:start])
        pieces.append(_rebuild(answer[start:body_start], answer[body_start:end], kept))
        cursor = end
    pieces.append(answer[cursor:])

    filtered = re.sub(r"\n{3,}", "\n\n", "".join(pieces)).strip()
    text, cited = resolve_citations(filtered, labels)
    return Verification(
        text=text,
        cited=cited,
        supported_claims=supported,
        dropped_claims=dropped,
        invalid_labels=sorted(set(invalid)),
    )


def resolve_citations(
    answer: str, labels: dict[str, RetrievedPassage]
) -> tuple[str, list[RetrievedPassage]]:
    """Geçerli [S#] etiketlerini ilk geçtikleri sırayla [1], [2]... yapar; bilinmeyenleri siler.

    İddia düzeyindeki ayıklama `verify_answer`'dadır; burada yalnızca bir cümlede geçerli
    etiketin yanında kalan uydurma etiketler ("[S1][S9]") temizlenir.
    """
    order: list[str] = []
    for label in _LABEL.findall(answer):
        if label in labels and label not in order:
            order.append(label)
    numbers = {label: index for index, label in enumerate(order, start=1)}

    def renumber(match: re.Match[str]) -> str:
        number = numbers.get(match.group(2))
        return f"{match.group(1)}[{number}]" if number else ""

    return _LABEL_WITH_SPACE.sub(renumber, answer), [labels[label] for label in order]


def _blocks(text: str) -> Iterator[tuple[int, int]]:
    """Kod blokları ve başlıklar dışındaki paragraflar ve liste maddeleri: (başlangıç, bitiş)."""
    code = [(match.start(), match.end()) for match in _FENCE.finditer(text)]
    offset = 0
    paragraph: int | None = None
    for line in text.splitlines(keepends=True):
        start = offset
        offset += len(line)
        in_code = any(code_start <= start < code_end for code_start, code_end in code)
        skip = in_code or not line.strip() or bool(_HEADING.match(line))
        item = not skip and bool(_LIST_ITEM.match(line))
        if (skip or item) and paragraph is not None:
            yield paragraph, start
            paragraph = None
        if item:
            yield start, offset
        elif not skip and paragraph is None:
            paragraph = start
    if paragraph is not None:
        yield paragraph, offset


def _sentences(text: str, start: int, end: int) -> list[_Sentence]:
    spans: list[tuple[int, int]] = []
    cursor = start
    for match in _SENTENCE_END.finditer(text, start, end):
        spans.append((cursor, match.end()))
        cursor = match.end()
    if text[cursor:end].strip():
        spans.append((cursor, end))

    sentences = []
    for span_start, span_end in spans:
        body = text[span_start:span_end]
        labels = _LABEL.findall(body)
        words = len(_WORD.findall(_LABEL.sub("", body)))
        claim = bool(labels) or (words >= MIN_CLAIM_WORDS and not body.rstrip().endswith(":"))
        sentences.append(_Sentence(span_start, span_end, labels, claim))
    return sentences


def _rebuild(marker: str, body: str, kept: list[str]) -> str:
    """Bloğu yalnızca kalan cümlelerle yeniden kurar; boş kalan madde/paragraf tamamen düşer."""
    if not kept:
        return ""
    indent = body[: len(body) - len(body.lstrip())]
    trailing = body[len(body.rstrip()) :]
    return marker + indent + " ".join(kept) + trailing
