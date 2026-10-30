"""İnsan örneklemi metrikleri: pratik kabulü, değerlendirme QWK'si, SUS ve memnuniyet.

Kullanım (evaluation/ içinden):

    python -m harness.pilot --labels human_labels/pilot/BLM2512 --out runs/

Girdi dosyaları metin içermez; kişi yerine takma ad kullanılır (`human_labels/README.md`):

- `practice_review.<takma-ad>.json` — eğitmen/TA'nın pratik sorusu incelemesi (`PracticeReviewSet`)
- `grading.<takma-ad>.json` — aynı öğrenci cevaplarına asistan ve eğitmen puanı (`GradingSet`)
- `survey.json` — gönüllülerin SUS ve memnuniyet cevapları (`SurveySet`)

Dosya yoksa ya da örneklem planlanandan küçükse metrik değer yerine boşlukla yazılır; eksik etiket
sentetik olarak doldurulmaz.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from harness.metrics import grading_agreement, practice_quality, usability
from harness.schemas import MetricValue

# Planlanan örneklem büyüklükleri (ANALYSIS §9).
PLANNED_PRACTICE_ITEMS = 40
PLANNED_GRADED_ANSWERS = 60
PLANNED_PARTICIPANTS = 20

Pseudonym = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,31}$")]
# Katılımcı kodu (ör. "p07"); öğrenci numarası ya da ad değil.
ParticipantCode = Annotated[str, StringConstraints(pattern=r"^p[0-9]{2,3}$")]
# Sistemdeki kaydın kimliği (pratik sorusu / deneme id'si); metin değil.
RecordRef = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,64}$")]

PracticeIssue = Literal[
    "incorrect",
    "answer_key_wrong",
    "not_supported_by_source",
    "ambiguous",
    "distractor_problem",
    "off_topic",
    "trivial",
    "other",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PracticeReview(_Strict):
    """Bir pratik sorusu için inceleme birimi: kabul edilebilir mi, değilse neden."""

    item_ref: RecordRef
    acceptable: bool
    issues: list[PracticeIssue] = []

    @model_validator(mode="after")
    def _issues_explain_rejection(self) -> Self:
        if not self.acceptable and not self.issues:
            raise ValueError(f"{self.item_ref}: kabul edilmeyen soruda en az bir neden gerekli")
        return self


class PracticeReviewSet(_Strict):
    schema_version: Literal[1] = 1
    course_code: str = Field(min_length=2, max_length=32)
    reviewer: Pseudonym
    reviewed_at: datetime
    # Gerçek iş yükü: incelemeye harcanan toplam dakika (değerlendirici kendisi yazar).
    minutes_spent: int | None = Field(default=None, ge=1)
    items: list[PracticeReview]


class GradedAnswer(_Strict):
    """Bir öğrenci cevabı: asistanın puanı (sistemden) ve eğitmenin bağımsız puanı."""

    attempt_ref: RecordRef
    assistant_score: int = Field(ge=0)
    instructor_score: int = Field(ge=0)


class GradingSet(_Strict):
    schema_version: Literal[1] = 1
    course_code: str = Field(min_length=2, max_length=32)
    rater: Pseudonym
    rated_at: datetime
    # Rubriğin puan aralığı (ör. 0–4); QWK bu aralıkla hesaplanır.
    min_score: int = Field(ge=0)
    max_score: int = Field(ge=1)
    # Eğitmen asistanın puanını görmeden mi puanladı (kör puanlama)?
    blind: bool
    # Gerçek iş yükü: puanlamaya harcanan toplam dakika.
    minutes_spent: int | None = Field(default=None, ge=1)
    items: list[GradedAnswer]

    @model_validator(mode="after")
    def _scores_in_range(self) -> Self:
        if self.max_score <= self.min_score:
            raise ValueError("max_score, min_score'dan büyük olmalı")
        for item in self.items:
            for score in (item.assistant_score, item.instructor_score):
                if not self.min_score <= score <= self.max_score:
                    raise ValueError(f"{item.attempt_ref}: puan {score} aralık dışında")
        return self


class SurveyResponse(_Strict):
    participant: ParticipantCode
    # Aydınlatma/onay metninin sürümü (ADR-4); onaysız cevap kaydedilmez.
    consent_version: str = Field(min_length=1, max_length=32)
    # SUS 10 madde (1–5); form eksikse None.
    sus: list[int] | None = Field(default=None, min_length=10, max_length=10)
    # Genel memnuniyet (1–5).
    satisfaction: int | None = Field(default=None, ge=1, le=5)


class SurveySet(_Strict):
    schema_version: Literal[1] = 1
    course_code: str = Field(min_length=2, max_length=32)
    # Kullanılan anket formunun sürümü (`instruments/README.md`).
    instrument_version: str = Field(min_length=1, max_length=32)
    responses: list[SurveyResponse]

    @model_validator(mode="after")
    def _unique_participants(self) -> Self:
        codes = [r.participant for r in self.responses]
        if len(codes) != len(set(codes)):
            raise ValueError("Aynı katılımcı iki kez")
        return self


class PilotReport(_Strict):
    created_at: datetime
    labels_dir: str
    metrics: dict[str, MetricValue]
    gaps: list[str]
    # Değerlendiricilerin yazdığı gerçek süre (birim başına dakika).
    workload: list[str] = []


def _value(
    compute, denominator: int, planned: int, target: str, numerator: int | None = None
) -> MetricValue:
    if denominator == 0:
        return MetricValue(value=None, denominator=0, target=target, gap="etiket yok")
    try:
        value = round(compute(), 4)
    except ValueError as exc:
        return MetricValue(value=None, denominator=denominator, target=target, gap=str(exc))
    gap = (
        f"örneklem {denominator}/{planned} (planlanandan küçük)" if denominator < planned else None
    )
    return MetricValue(
        value=value, numerator=numerator, denominator=denominator, target=target, gap=gap
    )


def practice_metrics(sets: Sequence[PracticeReviewSet]) -> dict[str, MetricValue]:
    """Her incelemeci için ayrı kabul oranı; iki incelemeci varsa ortak sorularda uyum oranı."""
    metrics: dict[str, MetricValue] = {}
    target = f">= {practice_quality.TARGET}"
    for review_set in sets:
        verdicts = [item.acceptable for item in review_set.items]
        metrics[f"practice_acceptable_rate.{review_set.reviewer}"] = _value(
            lambda v=verdicts: practice_quality.acceptable_rate(v),
            denominator=len(verdicts),
            numerator=sum(verdicts),
            planned=PLANNED_PRACTICE_ITEMS,
            target=target,
        )
    if len(sets) >= 2:
        first, second = sets[0], sets[1]
        a = {i.item_ref: i.acceptable for i in first.items}
        b = {i.item_ref: i.acceptable for i in second.items}
        common = sorted(a.keys() & b.keys())
        agree = sum(a[ref] == b[ref] for ref in common)
        metrics["practice_reviewer_agreement"] = _value(
            lambda: agree / len(common),
            denominator=len(common),
            numerator=agree,
            planned=PLANNED_PRACTICE_ITEMS,
            target="bilgi",
        )
    return metrics


def grading_metrics(sets: Sequence[GradingSet]) -> dict[str, MetricValue]:
    metrics: dict[str, MetricValue] = {}
    for grading in sets:
        assistant = [item.assistant_score for item in grading.items]
        instructor = [item.instructor_score for item in grading.items]
        metric = _value(
            lambda a=assistant, i=instructor, g=grading: grading_agreement.quadratic_weighted_kappa(
                a, i, g.min_score, g.max_score
            ),
            denominator=len(grading.items),
            planned=PLANNED_GRADED_ANSWERS,
            target=f">= {grading_agreement.TARGET}",
        )
        if not grading.blind:
            note = "eğitmen asistan puanını görerek puanladı (kör değil)"
            metric = metric.model_copy(update={"gap": "; ".join(filter(None, [metric.gap, note]))})
        metrics[f"grading_qwk.{grading.rater}"] = metric
    return metrics


def survey_metrics(survey: SurveySet | None) -> dict[str, MetricValue]:
    responses = survey.responses if survey else []
    sus = [r.sus for r in responses if r.sus is not None]
    satisfaction = [r.satisfaction for r in responses if r.satisfaction is not None]
    return {
        "sus_mean": _value(
            lambda: usability.sus_score(sus),
            denominator=len(sus),
            planned=PLANNED_PARTICIPANTS,
            target=f">= {usability.TARGET_SUS}",
        ),
        "satisfaction_mean": _value(
            lambda: usability.satisfaction_mean(satisfaction),
            denominator=len(satisfaction),
            planned=PLANNED_PARTICIPANTS,
            target=f">= {usability.TARGET_SATISFACTION}",
        ),
    }


def build_report(labels_dir: Path) -> PilotReport:
    gaps: list[str] = []
    practice = [
        PracticeReviewSet.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(labels_dir.glob("practice_review.*.json"))
    ]
    grading = [
        GradingSet.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(labels_dir.glob("grading.*.json"))
    ]
    survey_path = labels_dir / "survey.json"
    survey = (
        SurveySet.model_validate_json(survey_path.read_text(encoding="utf-8"))
        if survey_path.is_file()
        else None
    )
    if not practice:
        gaps.append(
            f"Pratik sorusu incelemesi yok (practice_review.*.json; plan: "
            f"{PLANNED_PRACTICE_ITEMS} soru, eğitmen/TA)"
        )
    if not grading:
        gaps.append(
            f"Öğrenci cevabı puanlaması yok (grading.*.json; plan: {PLANNED_GRADED_ANSWERS} "
            "cevap, eğitmen/TA kör puanlama)"
        )
    if survey is None:
        gaps.append(
            f"Anket cevabı yok (survey.json; plan: en az {PLANNED_PARTICIPANTS} onaylı gönüllü)"
        )
    workload: list[str] = []
    for label_set in [*practice, *grading]:
        alias = getattr(label_set, "reviewer", None) or getattr(label_set, "rater", "")
        if label_set.minutes_spent is None:
            gaps.append(f"{alias}: harcanan süre (minutes_spent) yazılmamış; iş yükü ölçülemedi")
        else:
            per_item = label_set.minutes_spent / max(len(label_set.items), 1)
            workload.append(
                f"{alias}: {len(label_set.items)} birim, {label_set.minutes_spent} dk "
                f"(birim başına {per_item:.1f} dk)"
            )
    metrics = {**practice_metrics(practice), **grading_metrics(grading), **survey_metrics(survey)}
    if not practice:
        metrics["practice_acceptable_rate"] = MetricValue(
            value=None, denominator=0, target=f">= {practice_quality.TARGET}", gap="etiket yok"
        )
    if not grading:
        metrics["grading_qwk"] = MetricValue(
            value=None, denominator=0, target=f">= {grading_agreement.TARGET}", gap="etiket yok"
        )
    return PilotReport(
        created_at=datetime.now(UTC),
        labels_dir=str(labels_dir),
        metrics=metrics,
        gaps=gaps,
        workload=workload,
    )


def render_markdown(report: PilotReport) -> str:
    from harness.report import metric_table

    lines = ["# İnsan örneklemi metrikleri", "", f"- Etiket klasörü: `{report.labels_dir}`"]
    lines += ["", *metric_table(report.metrics)]
    if report.workload:
        lines += ["", "## Değerlendirici iş yükü", "", *[f"- {w}" for w in report.workload]]
    if report.gaps:
        lines += ["", "## Boşluklar", "", *[f"- {gap}" for gap in report.gaps]]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.pilot", description=__doc__)
    parser.add_argument("--labels", type=Path, required=True, help="Etiket klasörü")
    parser.add_argument("--out", type=Path, help="Rapor klasörü (yoksa yalnızca ekrana yazılır)")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    report = build_report(args.labels)
    text = render_markdown(report)
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        stamp = report.created_at.strftime("%Y%m%dT%H%M%SZ")
        (args.out / f"pilot_{stamp}.json").write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (args.out / f"pilot_{stamp}.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
