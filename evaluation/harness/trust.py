"""Güvenilirlik raporu: koşu kaydı + insan etiketleri + judge etiketleri + kalibrasyon.

Kullanım (evaluation/ içinden):

    python -m harness.trust --run runs/<run_id>.json [--judge runs/<run_id>.judge.json]
    # → runs/<run_id>.trust.md

İnsan etiketleri `human_labels/<run_id>/` klasöründen (`sample.json` + değerlendirici dosyaları),
kalibrasyon `human_labels/judge_calibration.json`'dan okunur. Rapor metin içermez (yalnızca id,
sayı ve κ); anlaşmazlıkların metni etiketleme tablosundadır.

Judge kalibre değilse (ya da kalibrasyon bu judge/prompt/gold set için değilse) judge'a dayanan ana
metrikler değer yerine boşlukla yazılır; judge'ın sayıları ayrı tabloda "otoriter değil" diye durur.
İnsan etiketleri yalnızca örneklemdeki cevaplar için geçerlidir.
"""

import argparse
import itertools
import sys
from collections.abc import Sequence
from pathlib import Path

from harness.judge_agreement import (
    KAPPA_THRESHOLD,
    Agreement,
    Calibration,
    compare,
    judge_trust,
    load_calibration,
    load_label_dir,
    split_humans,
)
from harness.labels import (
    LabelSet,
    LabelSource,
    Sample,
    answerable_frame,
    claims_match,
    is_answered,
    load_sample,
)
from harness.metrics import accuracy, hallucination
from harness.report import fmt, header_lines, metric_table
from harness.schemas import MetricValue, RunRecord, Split, load_run

LABEL_METRICS = (
    "answer_fully_correct_rate",
    "answers_with_unsupported_claim_rate",
    "unsupported_claim_rate",
)
MAX_DISAGREEMENTS = 100


def label_metrics(
    record: RunRecord, labels: LabelSet, item_ids: set[str] | None = None
) -> dict[str, MetricValue]:
    """Bir değerlendiricinin etiketlerinden doğruluk ve hallucination; paydalar açık.

    Doğruluk paydası: kapsamdaki hatasız cevaplanabilir sorular (reddedilen cevap 0 puan).
    Hallucination paydası: bunların cevaplanmış olanları (cevap düzeyi) ve iddiaları (iddia
    düzeyi). Kapsamdaki bir cevap eksik etiketliyse metrik değer yerine boşlukla döner.
    """
    frame = [r for r in answerable_frame(record) if item_ids is None or r.id in item_ids]
    answered = [r for r in frame if is_answered(r)]
    by_item = labels.by_item()

    unscored = [r.id for r in answered if r.id not in by_item or by_item[r.id].score is None]
    if not frame:
        fully = MetricValue(value=None, denominator=0, gap="cevaplanabilir soru yok")
    elif unscored:
        fully = MetricValue(
            value=None, denominator=len(frame), gap=f"{len(unscored)} cevap puanlanmadı"
        )
    else:
        scores = [(by_item[r.id].score or 0) if is_answered(r) else 0 for r in frame]
        fully = MetricValue(
            value=round(accuracy.fully_correct_rate(scores), 4),
            numerator=scores.count(2),
            denominator=len(scores),
        )
    fully.target = f">= {accuracy.TARGET}"

    claim_lists: list[list[str]] = []
    incomplete = 0
    for result in answered:
        label = by_item.get(result.id)
        if label is None or not claims_match(label, result):
            incomplete += 1
        else:
            claim_lists.append([claim.label for claim in label.claims])
    flagged = sum(hallucination.UNSUPPORTED in labels_ for labels_ in claim_lists)
    claims = [label for labels_ in claim_lists for label in labels_]
    gap = f"{incomplete} cevabın iddiaları eksik etiketli" if incomplete else None
    if not answered:
        per_answer = MetricValue(value=None, denominator=0, gap="cevaplanmış soru yok")
        per_claim = MetricValue(value=None, denominator=0, gap="cevaplanmış soru yok")
    elif gap:
        per_answer = MetricValue(value=None, denominator=len(answered), gap=gap)
        per_claim = MetricValue(value=None, denominator=len(claims), gap=gap)
    else:
        per_answer = MetricValue(
            value=round(hallucination.answers_with_unsupported_claim_rate(claim_lists), 4),
            numerator=flagged,
            denominator=len(claim_lists),
        )
        per_claim = (
            MetricValue(
                value=round(hallucination.unsupported_claim_rate(claim_lists), 4),
                numerator=claims.count(hallucination.UNSUPPORTED),
                denominator=len(claims),
            )
            if claims
            else MetricValue(value=None, denominator=0, gap="cevaplarda iddia yok")
        )
    per_answer.target = f"<= {hallucination.TARGET_MAX}"
    return {
        "answer_fully_correct_rate": fully,
        "answers_with_unsupported_claim_rate": per_answer,
        "unsupported_claim_rate": per_claim,
    }


def headline_metrics(
    record: RunRecord, judge: LabelSet | None, distrust: str | None
) -> dict[str, MetricValue]:
    """`harness.run`'ın metrikleri; etiket gerektirenler yalnızca güvenilir judge'dan dolar."""
    metrics = dict(record.metrics)
    if judge is not None and distrust is None:
        metrics.update(label_metrics(record, judge))
        return metrics
    for name in LABEL_METRICS:
        base = metrics.get(name) or MetricValue(value=None, denominator=0)
        metrics[name] = base.model_copy(
            update={"value": None, "gap": f"judge sonuçları otoriter değil: {distrust}"}
        )
    return metrics


def _kappa_rows(agreements: Sequence[Agreement]) -> list[str]:
    return [
        f"| {a.left} – {a.right} | {a.kind} | {a.n} | {fmt(a.observed)} | {fmt(a.kappa)} | "
        f"{'✅' if a.passes() else '❌'} | {a.gap or ''} |"
        for a in agreements
    ]


def render_trust_report(
    record: RunRecord,
    sample: Sample | None,
    label_sets: Sequence[LabelSet],
    judge: LabelSet | None,
    calibration: Calibration | None,
) -> str:
    for labels in [*label_sets, *([judge] if judge else [])]:
        if labels.run_id != record.run_id:
            raise ValueError(f"{labels.rater} etiketleri başka bir koşuya ait ({labels.run_id})")
    if sample is not None and sample.run_id != record.run_id:
        raise ValueError(f"Örneklem başka bir koşuya ait ({sample.run_id})")
    humans = split_humans(label_sets)
    distrust = judge_trust(calibration, judge, record)
    gaps: list[str] = []

    lines = [f"# Güvenilirlik raporu `{record.run_id}`", "", *header_lines(record)]
    if judge is not None:
        status = "otoriter (kalibre)" if distrust is None else f"otoriter değil ({distrust})"
        lines.append(
            f"- Judge: `{judge.judge_model}` · prompt `{(judge.judge_prompt_sha256 or '')[:16]}…`"
            f" · {status}"
        )
    else:
        lines.append("- Judge: çalıştırılmadı")

    lines += [
        "",
        "## Ana metrikler",
        "",
        *metric_table(headline_metrics(record, judge, distrust)),
    ]

    sample_ids = set(sample.item_ids) if sample else None
    lines += ["", "## İnsan etiketleri", ""]
    if sample is not None:
        lines.append(
            f"Örneklem: {len(sample.item_ids)}/{sample.frame_size} cevaplanabilir soru, tohum "
            f"{sample.seed} (`human_labels/{record.run_id}/sample.json`). Reddedilen cevaplar "
            "0 puan sayılır ve etiketlenmez."
        )
    else:
        gaps.append("İnsan etiketleme örneklemi yok (harness.labels sample)")
    if not humans:
        lines.append("İnsan etiketi yok.")
        gaps.append("İnsan etiketi yok: insan değerlendiriciler henüz etiketlemedi")
    for human in humans:
        lines += [
            "",
            f"### {human.rater}",
            "",
            *metric_table(label_metrics(record, human, sample_ids)),
        ]
    if len(humans) < 2:
        gaps.append(f"İnsan değerlendirici {len(humans)}/2: insanlar arası uyum ölçülemiyor")

    if judge is not None:
        title = "Judge sonuçları" if distrust is None else "Judge ön sonuçları (otoriter değil)"
        lines += ["", f"## {title}", "", *metric_table(label_metrics(record, judge))]

    inter = [a for left, right in itertools.combinations(humans, 2) for a in compare(left, right)]
    judge_human = [a for human in humans for a in compare(judge, human)] if judge else []
    lines += [
        "",
        f"## Uyum (Cohen's κ, eşik {KAPPA_THRESHOLD})",
        "",
        "| Çift | Tür | n | Gözlenen uyum | κ | Eşik | Not |",
        "|---|---|---|---|---|---|---|",
        *_kappa_rows(inter),
        *_kappa_rows(judge_human),
    ]
    if not inter and not judge_human:
        lines.append("| — | — | 0 | — | — | — | karşılaştırılacak iki etiket kümesi yok |")
    if record.config.split is Split.HELDOUT:
        lines += [
            "",
            "Bu koşu held-out: buradaki judge–insan uyumu yalnızca doğrulamadır, judge ayarında "
            "kullanılmaz.",
        ]
    if calibration is not None:
        verdict = "geçti" if calibration.passed else "geçmedi"
        lines += [
            "",
            f"Kalibrasyon (`{calibration.run_id}`, judge `{calibration.judge_model}`): {verdict}.",
        ]
        lines += [f"- {reason}" for reason in calibration.reasons]

    disagreements = [(a, d) for a in [*inter, *judge_human] for d in a.disagreements]
    if disagreements:
        lines += [
            "",
            "## Anlaşmazlıklar",
            "",
            "Metinler etiketleme tablosunda (soru id + iddia sırası).",
            "",
            "| Çift | Tür | Soru | İddia | Sol | Sağ |",
            "|---|---|---|---|---|---|",
        ]
        for agreement, d in disagreements[:MAX_DISAGREEMENTS]:
            claim = "" if d.claim_index is None else str(d.claim_index)
            lines.append(
                f"| {agreement.left} – {agreement.right} | {agreement.kind} | `{d.item_id}` | "
                f"{claim} | {d.left} | {d.right} |"
            )
        if len(disagreements) > MAX_DISAGREEMENTS:
            lines.append(f"\n… ve {len(disagreements) - MAX_DISAGREEMENTS} anlaşmazlık daha")

    if distrust is not None:
        gaps.append(f"Judge sonuçları otoriter değil: {distrust}")
    gaps += record.gaps
    lines += ["", "## Boşluklar", ""]
    lines += [f"- {gap}" for gap in gaps] or ["- Yok"]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.trust", description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--judge", type=Path, help="Varsayılan: runs/<run_id>.judge.json (varsa)")
    parser.add_argument("--labels", type=Path, help="Varsayılan: human_labels/<run_id>/")
    parser.add_argument(
        "--calibration", type=Path, default=Path("human_labels/judge_calibration.json")
    )
    parser.add_argument("--out", type=Path, help="Varsayılan: runs/<run_id>.trust.md")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    # Windows konsolu (cp1254) Türkçe karakterleri bozmasın.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    record = load_run(args.run)
    folder = args.labels or Path("human_labels") / record.run_id
    sample = load_sample(folder / "sample.json") if (folder / "sample.json").is_file() else None
    judge_path = args.judge or args.run.with_suffix(".judge.json")
    judge = None
    if judge_path.is_file():
        judge = LabelSet.model_validate_json(judge_path.read_text(encoding="utf-8"))
        if judge.source is not LabelSource.JUDGE or judge.run_id != record.run_id:
            raise SystemExit("Judge dosyası bu koşunun judge etiketleri değil")
    report = render_trust_report(
        record,
        sample,
        load_label_dir(folder),
        judge,
        load_calibration(args.calibration),
    )
    out = args.out or args.run.with_suffix(".trust.md")
    out.write_text(report, encoding="utf-8")
    print(f"Güvenilirlik raporu: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
