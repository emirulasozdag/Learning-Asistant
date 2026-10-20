"""Uyum: insan–insan ve judge–insan Cohen's κ, anlaşmazlık listesi ve judge kalibrasyonu.

Judge'a ancak kalibrasyon split'inde her insan değerlendiriciyle hem cevap puanında hem iddia
etiketinde κ ≥ KAPPA_THRESHOLD ise güvenilir. Kalibrasyon yalnızca `calibration` split'i koşusundan
yapılır; held-out etiketleri judge ayarında kullanılmaz, yalnızca raporda doğrulama olarak görünür.

Kullanım (evaluation/ içinden):

    python -m harness.judge_agreement --run runs/<kalibrasyon_run_id>.json \
        --judge runs/<kalibrasyon_run_id>.judge.json
    # → human_labels/judge_calibration.json (geçti/geçmedi ve gerekçeleri)
"""

import argparse
import itertools
import sys
from collections import Counter
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from harness.labels import LabelSet, LabelSource, load_labels
from harness.schemas import SCHEMA_VERSION, RunRecord, Sha256, Split, _Strict, load_run

KAPPA_THRESHOLD = 0.6
# docs/ANALYSIS.md §9: iki değerlendirici, koşul başına 40 cevap.
MIN_CALIBRATION_ANSWERS = 40
MIN_HUMAN_RATERS = 2

Kind = Literal["score", "claim"]


def cohen_kappa(left: Sequence[Hashable], right: Sequence[Hashable]) -> float:
    """İki değerlendirici arasında Cohen's κ (ağırlıksız, sınıflar etiketlerden çıkarılır).

    Boş liste ya da iki tarafın da tek ve aynı sınıfı kullandığı durum (beklenen uyum 1, κ
    tanımsız) ValueError verir.
    """
    if len(left) != len(right):
        raise ValueError("İki etiket listesi aynı uzunlukta olmalı")
    if not left:
        raise ValueError("κ: payda sıfır")
    n = len(left)
    observed = sum(a == b for a, b in zip(left, right, strict=True)) / n
    left_counts, right_counts = Counter(left), Counter(right)
    expected = sum(left_counts[c] * right_counts[c] for c in left_counts) / (n * n)
    if expected == 1:
        raise ValueError("κ tanımsız: iki taraf da yalnızca tek bir sınıf kullanmış")
    return (observed - expected) / (1 - expected)


@dataclass
class Disagreement:
    item_id: str
    claim_index: int | None
    left: str
    right: str


@dataclass
class Agreement:
    left: str
    right: str
    kind: Kind
    n: int
    kappa: float | None
    observed: float | None
    gap: str | None = None
    disagreements: list[Disagreement] = field(default_factory=list)

    def passes(self, threshold: float = KAPPA_THRESHOLD) -> bool:
        return self.kappa is not None and self.kappa >= threshold


def _agreement(
    left: LabelSet,
    right: LabelSet,
    kind: Kind,
    pairs: list[tuple[str, int | None, str, str]],
) -> Agreement:
    a = [pair[2] for pair in pairs]
    b = [pair[3] for pair in pairs]
    disagreements = [Disagreement(i, c, x, y) for i, c, x, y in pairs if x != y]
    observed = (len(pairs) - len(disagreements)) / len(pairs) if pairs else None
    try:
        # Ham değer saklanır: yuvarlama eşiğin hemen altındaki κ'yı (0,59996) geçirmesin.
        kappa, gap = cohen_kappa(a, b), None
    except ValueError as exc:
        kappa, gap = None, str(exc)
    return Agreement(
        left=left.rater,
        right=right.rater,
        kind=kind,
        n=len(pairs),
        kappa=kappa,
        observed=round(observed, 4) if observed is not None else None,
        gap=gap,
        disagreements=disagreements,
    )


def compare(left: LabelSet, right: LabelSet) -> tuple[Agreement, Agreement]:
    """Cevap puanında ve iddia etiketinde uyum; yalnızca iki tarafın da etiketlediği birimler.

    İddialar (soru, sıra) ile eşleşir ve metin parmak izleri aynı olmalıdır; farklıysa (cevap ya
    da bölme kuralı değişmiş) o iddia karşılaştırılmaz ve boşluk olarak yazılır.
    """
    if left.run_id != right.run_id:
        raise ValueError(
            f"Farklı koşuların etiketleri karşılaştırılamaz: {left.rater}/{right.rater}"
        )
    right_items = right.by_item()
    scores: list[tuple[str, int | None, str, str]] = []
    claims: list[tuple[str, int | None, str, str]] = []
    stale = 0
    for item in left.items:
        other = right_items.get(item.item_id)
        if other is None:
            continue
        if item.score is not None and other.score is not None:
            scores.append((item.item_id, None, str(item.score), str(other.score)))
        other_claims = {claim.index: claim for claim in other.claims}
        for claim in item.claims:
            match = other_claims.get(claim.index)
            if match is None:
                continue
            if match.claim_sha256 != claim.claim_sha256:
                stale += 1
                continue
            claims.append((item.item_id, claim.index, claim.label, match.label))
    score_agreement = _agreement(left, right, "score", scores)
    claim_agreement = _agreement(left, right, "claim", claims)
    if stale:
        note = f"{stale} iddianın metni iki tarafta farklı; karşılaştırılmadı"
        claim_agreement.gap = f"{claim_agreement.gap}; {note}" if claim_agreement.gap else note
    return score_agreement, claim_agreement


# --- Kalibrasyon -------------------------------------------------------------------------------


class KappaEntry(_Strict):
    left: str
    right: str
    kind: Kind
    n: int
    kappa: float | None
    gap: str | None = None


class Calibration(_Strict):
    """Judge kalibrasyonunun sonucu. Metin içermez; git'e girer."""

    schema_version: Literal[1] = SCHEMA_VERSION
    judge_model: str
    judge_prompt_sha256: Sha256
    run_id: str
    gold_set_sha256: str
    threshold: float
    human_raters: list[str]
    inter_rater: list[KappaEntry]
    judge_human: list[KappaEntry]
    passed: bool
    reasons: list[str]
    created_at: datetime


def _show(kappa: float | None) -> str:
    return "—" if kappa is None else f"{kappa:.3f}"


def _entry(agreement: Agreement) -> KappaEntry:
    return KappaEntry(
        left=agreement.left,
        right=agreement.right,
        kind=agreement.kind,
        n=agreement.n,
        kappa=agreement.kappa,
        gap=agreement.gap,
    )


def split_humans(label_sets: Sequence[LabelSet]) -> list[LabelSet]:
    humans = [labels for labels in label_sets if labels.source is LabelSource.HUMAN]
    raters = [labels.rater for labels in humans]
    if len(raters) != len(set(raters)):
        raise ValueError("Aynı takma adla iki insan etiket dosyası var")
    return humans


def calibrate(
    record: RunRecord,
    humans: Sequence[LabelSet],
    judge: LabelSet,
    threshold: float = KAPPA_THRESHOLD,
    now: datetime | None = None,
) -> Calibration:
    if record.config.split is not Split.CALIBRATION:
        raise ValueError(
            "Kalibrasyon yalnızca calibration split'i koşusuyla yapılır; "
            "held-out ayarda kullanılmaz"
        )
    if judge.source is not LabelSource.JUDGE:
        raise ValueError("Judge etiket dosyası judge kaynaklı değil")
    for labels in [*humans, judge]:
        if labels.run_id != record.run_id:
            raise ValueError(f"{labels.rater} etiketleri başka bir koşuya ait ({labels.run_id})")

    reasons: list[str] = []
    if len(humans) < MIN_HUMAN_RATERS:
        reasons.append(f"İnsan değerlendirici {len(humans)}/{MIN_HUMAN_RATERS}")
    inter_rater: list[Agreement] = []
    for left, right in itertools.combinations(humans, 2):
        inter_rater += compare(left, right)
    judge_human: list[Agreement] = []
    for human in humans:
        judge_human += compare(judge, human)

    for agreement in inter_rater:
        if not agreement.passes(threshold):
            reasons.append(
                f"İnsanlar arası uyum yetersiz ({agreement.left}–{agreement.right}, "
                f"{agreement.kind}: κ={_show(agreement.kappa)}); önce rubrik netleştirilmeli"
            )
    for agreement in judge_human:
        if agreement.n < MIN_CALIBRATION_ANSWERS and agreement.kind == "score":
            reasons.append(
                f"Judge–{agreement.right} ortak puanlı cevap {agreement.n}/"
                f"{MIN_CALIBRATION_ANSWERS}"
            )
        if not agreement.passes(threshold):
            reasons.append(
                f"Judge–{agreement.right} {agreement.kind} uyumu κ={_show(agreement.kappa)} "
                f"(eşik {threshold})" + (f": {agreement.gap}" if agreement.gap else "")
            )
    return Calibration(
        judge_model=judge.judge_model or "",
        judge_prompt_sha256=judge.judge_prompt_sha256 or "0" * 64,
        run_id=record.run_id,
        gold_set_sha256=record.config.gold_set_sha256,
        threshold=threshold,
        human_raters=[labels.rater for labels in humans],
        inter_rater=[_entry(a) for a in inter_rater],
        judge_human=[_entry(a) for a in judge_human],
        passed=not reasons,
        reasons=reasons,
        created_at=now or datetime.now(UTC),
    )


def judge_trust(
    calibration: Calibration | None, judge: LabelSet | None, record: RunRecord
) -> str | None:
    """Judge bu koşu için otoriter mi? Evetse None, değilse nedeni."""
    if judge is None:
        return "judge çalıştırılmadı"
    if calibration is None:
        return "judge kalibre edilmedi"
    if not calibration.passed:
        return "judge kalibrasyonu κ eşiğini geçmedi"
    if (calibration.judge_model, calibration.judge_prompt_sha256) != (
        judge.judge_model,
        judge.judge_prompt_sha256,
    ):
        return "kalibre edilen judge (model/prompt) bu etiketleri üretenle aynı değil"
    if calibration.gold_set_sha256 != record.config.gold_set_sha256:
        return "kalibrasyon başka bir gold set sürümüyle yapıldı"
    return None


def load_label_dir(folder: Path) -> list[LabelSet]:
    """Klasördeki etiket dosyaları (`sample.json` hariç)."""
    if not folder.is_dir():
        return []
    return [
        load_labels(path) for path in sorted(folder.glob("*.json")) if path.name != "sample.json"
    ]


def load_calibration(path: Path) -> Calibration | None:
    if not path.is_file():
        return None
    return Calibration.model_validate_json(path.read_text(encoding="utf-8"))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.judge_agreement", description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="calibration split koşusu")
    parser.add_argument("--judge", type=Path, required=True, help="judge etiketleri")
    parser.add_argument("--labels", type=Path, help="Varsayılan: human_labels/<run_id>/")
    parser.add_argument("--out", type=Path, default=Path("human_labels/judge_calibration.json"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    # Windows konsolu (cp1254) Türkçe karakterleri bozmasın.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    record = load_run(args.run)
    humans = split_humans(load_label_dir(args.labels or Path("human_labels") / record.run_id))
    try:
        calibration = calibrate(record, humans, load_labels(args.judge))
    except ValueError as exc:
        print(f"Kalibrasyon yapılmadı: {exc}", file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(calibration.model_dump_json(indent=2), encoding="utf-8")
    print(f"Kalibrasyon {'GEÇTİ' if calibration.passed else 'GEÇMEDİ'}: {args.out}")
    for reason in calibration.reasons:
        print(f"  neden: {reason}")
    return 0 if calibration.passed else 1


if __name__ == "__main__":
    sys.exit(main())
