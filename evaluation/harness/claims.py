"""Cevabı etiketlenecek iddia birimlerine böler.

İnsan değerlendiriciler ve judge aynı birimleri etiketlemeli, yoksa iddia düzeyinde uyum (κ)
hesaplanamaz. Bu yüzden bölme belirlenimcidir: paragraf / liste maddesi / cümle. Alıntı işaretleri
("[1]", "[S2]") atılır; başlıklar, kod blokları, ":" ile biten giriş cümleleri ve üç kelimeden kısa
parçalar iddia sayılmaz. Her iddia metninin parmak izi etiketlerde tutulur; cevap ya da bölme
kuralı değişirse eski etiket yeni iddiayla eşleştirilmez.
"""

import re

from harness.fingerprint import text_sha256

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_MARKER = re.compile(r"\s*\[(?:S)?\d+\]")
_LIST_ITEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")
_WORD = re.compile(r"\w+")
MIN_WORDS = 3


def split_claims(answer: str) -> list[str]:
    claims: list[str] = []
    for line in _FENCE.sub("\n", answer).splitlines():
        if _HEADING.match(line):
            continue
        line = _MARKER.sub("", _LIST_ITEM.sub("", line)).strip()
        for sentence in _SENTENCE_END.split(line):
            sentence = " ".join(sentence.split())
            if not sentence or sentence.endswith(":"):
                continue
            if len(_WORD.findall(sentence)) < MIN_WORDS:
                continue
            claims.append(sentence)
    return claims


def claim_sha256(claim: str) -> str:
    return text_sha256(claim)
