"""Cevabın iddia kontrolü (FR-14): iddia birimleri → judge → desteklenmeyenlerin çıkarılması.

Akış (`generation/answer.py`):
1. Alıntı doğrulaması (`citations.verify_answer`) geçmezse judge çağrılmaz.
2. `check_claims`: iddia birimleri judge'a gider; desteklenmeyen birimler (bağlı etiketsiz
   cümleleriyle) metinden çıkarılır.
3. Kalan metin yeniden `verify_answer`'dan geçer; judge'ın çıkardıkları da sayılarak kapsama
   yetmezse cevap reddedilir.

CLAIM_CHECK=required iken judge yoksa ya da başarısızsa üretilen metin gösterilmez.

Görsel kanıt (#26): bir kareyi alıntılayan birimler metin judge'ına gitmez; karenin görüntüsüyle
kontrol edilir (`verification/visual.py`). Kare verilmeyen (yalnızca metin) cevapta akış ve judge
isteği önceki gibidir.
"""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.generation.visual import VisualEvidence
from app.llm.base import LLMClient, LLMError
from app.retrieval.types import RetrievedPassage
from app.schemas.ask import ClaimCheck
from app.verification.citations import ClaimUnit, claim_units, remove_claims
from app.verification.judge import JUDGE_PROMPT_VERSION, ClaimLabel, label_claims
from app.verification.visual import (
    VISUAL_JUDGE_PROMPT_VERSION,
    VisualClaimLabel,
    label_visual_claims,
)

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "İddia kontrolü için judge yapılandırılmadı (JUDGE_PROVIDER, JUDGE_MODEL)."


@dataclass
class CheckedText:
    """Judge'ın reddettiği iddiaları çıkarılmış cevap ve kontrol özeti."""

    text: str
    check: ClaimCheck
    # Cevaptan çıkarılan iddia birimleri: desteklenmeyen, ayrıca görsel iddialarda kontrol
    # edilemeyen (unverifiable) ve belirsiz (ambiguous) olanlar. Yalnızca metinde = unsupported.
    removed: int = 0
    # Görüntüde ne kastedildiği belli olmadığı için çıkarılanlar (netleştirme isteği için).
    ambiguous: int = 0
    # Görüntüsü judge'a gönderilen karelerin kimlikleri (kontrol sonra başarısız olsa da).
    images_sent: list[int] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Metin öğrenciye gösterilebilir mi (kontrol edildi ya da kontrol kapalı)."""
        return self.check.status in ("checked", "off")


def split_into_claims(answer: str, labels: dict[str, RetrievedPassage]) -> list[ClaimUnit]:
    """Cevabı judge'a gidecek iddia birimlerine böler (her birim kendi kaynaklarıyla)."""
    return claim_units(answer, labels)[1]


def check_claims(
    answer: str,
    labels: dict[str, RetrievedPassage],
    judge: LLMClient | None,
    mode: str,
    judge_error: str | None = None,
    frames: Mapping[str, VisualEvidence] | None = None,
) -> CheckedText:
    """`mode`: "required" ya da "off" (CLAIM_CHECK). `judge_error`: judge seçilirken oluşan
    yapılandırma hatası (ör. generator'la aynı aile); kontrol başarısız sayılır.

    `frames`: kare etiketleri (#26). Kareyi alıntılayan birimler görüntüyle kontrol edilir;
    `mode="off"` iken de kontrol edilmeden gösterilmez, çıkarılır.
    """
    frames = dict(frames or {})
    if mode == "off":
        if frames:
            return _drop_unchecked_visual(answer, labels, frames)
        return CheckedText(answer, ClaimCheck(status="off"))
    if judge is None:
        status = "failed" if judge_error else "not_configured"
        return CheckedText(answer, ClaimCheck(status=status, error=judge_error or NOT_CONFIGURED))

    expanded, units = claim_units(answer, labels)
    visual = [_cites_frame(unit, frames) for unit in units]
    text_units = [unit for unit, is_visual in zip(units, visual, strict=True) if not is_visual]
    visual_units = [unit for unit, is_visual in zip(units, visual, strict=True) if is_visual]
    check = ClaimCheck(
        status="checked",
        judge_model=judge.model,
        claims=len(units),
        prompt_version=(
            f"{JUDGE_PROMPT_VERSION}+{VISUAL_JUDGE_PROMPT_VERSION}"
            if visual_units
            else JUDGE_PROMPT_VERSION
        ),
    )
    # Görüntüsü judge'a gerçekten gönderilen kareler; istek gitmezse (ör. metin judge'ı önce hata
    # verdi) boş kalır.
    images_sent: list[int] = []
    try:
        text_results = iter(label_claims(text_units, labels, judge))
        visual_results = iter(
            label_visual_claims(visual_units, labels, frames, judge, sent=images_sent)
            if visual_units
            else []
        )
    except LLMError as exc:
        logger.warning("İddia kontrolü yapılamadı (%s): %s", judge.model, exc)
        check.status = "failed"
        check.error = str(exc)
        return CheckedText(answer, check, images_sent=images_sent)

    # Cevaptaki sıraya göre birleştirilir; kayıttaki iddia kimlikleri de bu sırayla verilir.
    results: list[ClaimLabel] = [
        next(visual_results) if is_visual else next(text_results) for is_visual in visual
    ]
    for index, result in enumerate(results, start=1):
        result.claim_id = f"C{index}"
    rejected = [
        unit.span
        for unit, result in zip(units, results, strict=True)
        if result.label != "supported"
    ]
    check.unsupported = sum(result.label == "unsupported" for result in results)
    check.records = [result.to_record() for result in results]
    strips = _unvalidated_frame_labels(expanded, units, results, labels)
    if strips:
        text = remove_claims(*_strip_labels(expanded, strips, rejected))
    else:
        text = remove_claims(expanded, rejected) if rejected else answer
    return CheckedText(
        text,
        check,
        removed=len(rejected),
        ambiguous=sum(result.label == "ambiguous" for result in results),
        images_sent=images_sent,
    )


_LABEL_TOKEN = re.compile(r"\[(S\d+)\]")


def _unvalidated_frame_labels(
    expanded: str,
    units: list[ClaimUnit],
    results: list[ClaimLabel],
    labels: dict[str, RetrievedPassage],
) -> list[tuple[int, int]]:
    """Kalan iddialardaki, görüntüden doğrulanmamış kare etiketlerinin metindeki yerleri."""
    strips: list[tuple[int, int]] = []
    for unit, result in zip(units, results, strict=True):
        if result.label != "supported" or not isinstance(result, VisualClaimLabel):
            continue
        dropped = set(result.dropped_frame_citations)
        for match in _LABEL_TOKEN.finditer(expanded, unit.span[0], unit.span[1]):
            if match.group(1) in labels and labels[match.group(1)].source_id in dropped:
                strips.append((match.start(), match.end()))
    return strips


def _strip_labels(
    text: str, strips: list[tuple[int, int]], spans: list[tuple[int, int]]
) -> tuple[str, list[tuple[int, int]]]:
    """Etiketleri siler; reddedilen birimlerin aralıklarını silinen uzunluk kadar kaydırır.
    Etiketler kalan birimlerin içindedir, reddedilen aralıklarla örtüşmez."""
    for start, end in sorted(strips, reverse=True):
        text = text[:start] + text[end:]

    def shift(position: int) -> int:
        return position - sum(end - start for start, end in strips if end <= position)

    return text, [(shift(start), shift(end)) for start, end in spans]


def _cites_frame(unit: ClaimUnit, frames: Mapping[str, VisualEvidence]) -> bool:
    return any(label in frames for label in unit.labels)


def _drop_unchecked_visual(
    answer: str, labels: dict[str, RetrievedPassage], frames: dict[str, VisualEvidence]
) -> CheckedText:
    """CLAIM_CHECK=off iken kareyi alıntılayan birimler kontrol edilemez: çıkarılır ve kayda
    `unverifiable` olarak yazılır. Kareye dayanan iddia türetilmiş metinle kabul edilmez."""
    expanded, units = claim_units(answer, labels)
    dropped = [unit for unit in units if _cites_frame(unit, frames)]
    check = ClaimCheck(status="off")
    if not dropped:
        return CheckedText(answer, check)
    check.records = [
        VisualClaimLabel(
            claim_id="",
            claim=unit.text,
            cited_source_ids=[labels[label].source_id for label in unit.labels],
            label="unverifiable",
            judge_model="",
            reason="not_checked",
            frames=[frames[label].provenance(False) for label in unit.labels if label in frames],
        ).to_record()
        for unit in dropped
    ]
    return CheckedText(
        remove_claims(expanded, [unit.span for unit in dropped]), check, removed=len(dropped)
    )
