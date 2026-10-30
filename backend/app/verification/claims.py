"""Cevabın iddia kontrolü (FR-14): iddia birimleri → judge → desteklenmeyenlerin çıkarılması.

Akış (`generation/answer.py`):
1. Alıntı doğrulaması (`citations.verify_answer`) geçmezse judge çağrılmaz.
2. `check_claims`: iddia birimleri judge'a gider; desteklenmeyen birimler (bağlı etiketsiz
   cümleleriyle) metinden çıkarılır.
3. Kalan metin yeniden `verify_answer`'dan geçer; judge'ın çıkardıkları da sayılarak kapsama
   yetmezse cevap reddedilir.

CLAIM_CHECK=required iken judge yoksa ya da başarısızsa üretilen metin gösterilmez.
"""

import logging
from dataclasses import dataclass

from app.llm.base import LLMClient, LLMError
from app.retrieval.types import RetrievedPassage
from app.schemas.ask import ClaimCheck
from app.verification.citations import ClaimUnit, claim_units, remove_claims
from app.verification.judge import JUDGE_PROMPT_VERSION, label_claims

logger = logging.getLogger(__name__)

NOT_CONFIGURED = "İddia kontrolü için judge yapılandırılmadı (JUDGE_PROVIDER, JUDGE_MODEL)."


@dataclass
class CheckedText:
    """Judge'ın reddettiği iddiaları çıkarılmış cevap ve kontrol özeti."""

    text: str
    check: ClaimCheck

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
) -> CheckedText:
    """`mode`: "required" ya da "off" (CLAIM_CHECK). `judge_error`: judge seçilirken oluşan
    yapılandırma hatası (ör. generator'la aynı aile); kontrol başarısız sayılır."""
    if mode == "off":
        return CheckedText(answer, ClaimCheck(status="off"))
    if judge is None:
        status = "failed" if judge_error else "not_configured"
        return CheckedText(answer, ClaimCheck(status=status, error=judge_error or NOT_CONFIGURED))

    expanded, units = claim_units(answer, labels)
    check = ClaimCheck(
        status="checked",
        judge_model=judge.model,
        claims=len(units),
        prompt_version=JUDGE_PROMPT_VERSION,
    )
    try:
        results = label_claims(units, labels, judge)
    except LLMError as exc:
        logger.warning("İddia kontrolü yapılamadı (%s): %s", judge.model, exc)
        check.status = "failed"
        check.error = str(exc)
        return CheckedText(answer, check)

    rejected = [
        unit.span
        for unit, result in zip(units, results, strict=True)
        if result.label == "unsupported"
    ]
    check.unsupported = len(rejected)
    check.records = [result.to_record() for result in results]
    return CheckedText(remove_claims(expanded, rejected) if rejected else answer, check)
