"""İnsan ve judge etiketleri: şema, örneklem, etiketleme tablosu (CSV) üretme ve geri okuma.

Kullanım (evaluation/ içinden):

    # 1. Belgelenmiş örneklem: cevaplanabilir sorulardan sabit tohumla seçilir.
    python -m harness.labels sample --run runs/<run_id>.json --size 40 --seed 13
    # 2. Boş etiketleme tablosu (soru, referans, cevap, pasajlar, iddialar). Metin içerir: git'e
    #    girmez, varsayılan yeri runs/.
    python -m harness.labels sheet --run runs/<run_id>.json --gold gold_sets/BLM2512/gold_set.json
    # 3. Her değerlendirici tablonun kendi kopyasını doldurur (score ve label sütunları).
    # 4. Doldurulan tablo geri okunur; çıktı metin içermez (yalnızca id, iddia parmak izi, etiket).
    python -m harness.labels import --run runs/<run_id>.json --sheet dolu.csv --rater rater-a

Değerlendirici adı yerine takma ad kullanılır (ör. `rater-a`); kişisel veri yazılmaz.
"""

import argparse
import csv
import random
import sys
from collections.abc import Collection, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from harness.claims import claim_sha256, split_claims
from harness.fingerprint import file_sha256
from harness.schemas import (
    SCHEMA_VERSION,
    GoldSet,
    ItemKind,
    ItemResult,
    RunRecord,
    Sha256,
    SourceLocator,
    Split,
    _Strict,
    load_gold_set,
    load_run,
)

# Takma ad: küçük harf, rakam ve tire ("rater-a", "ta-2"). Gerçek ad ya da e-posta yazılmaz.
Pseudonym = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{1,31}$")]
ClaimVerdict = Literal["supported", "unsupported"]

# Excel'in hücre sınırı 32 767 karakter; pasajlar bunun altında kesilir.
_CELL_LIMIT = 30_000
SHEET_COLUMNS = [
    "run_id",
    "item_id",
    "row",
    "claim_index",
    "claim_sha256",
    "question",
    "reference_answer",
    "answer",
    "passages",
    "claim",
    "score",
    "label",
    "note",
]
_VERDICTS = {
    "supported": "supported",
    "s": "supported",
    "unsupported": "unsupported",
    "u": "unsupported",
}


class LabelSource(StrEnum):
    HUMAN = "human"
    JUDGE = "judge"


class ClaimLabel(_Strict):
    index: int = Field(ge=0)
    # Etiketlenen iddia metninin parmak izi; cevap ya da bölme kuralı değişirse eşleşmez.
    claim_sha256: Sha256
    label: ClaimVerdict


class AnswerLabel(_Strict):
    item_id: str
    # 0 = yanlış, 1 = kısmen doğru / eksik, 2 = tamamen doğru (eğitmen referansına göre).
    # None: puanlanmadı (ör. referans cevap yok).
    score: int | None = Field(default=None, ge=0, le=2)
    claims: list[ClaimLabel] = []

    @model_validator(mode="after")
    def _unique_claims(self) -> Self:
        indexes = [claim.index for claim in self.claims]
        if len(indexes) != len(set(indexes)):
            raise ValueError(f"{self.item_id}: aynı iddia iki kez etiketlenmiş")
        return self


class LabelSet(_Strict):
    """Bir değerlendiricinin (insan ya da judge) bir koşu üzerindeki etiketleri."""

    schema_version: Literal[1] = SCHEMA_VERSION
    run_id: str
    source: LabelSource
    rater: Pseudonym
    judge_model: str | None = None
    judge_prompt_sha256: Sha256 | None = None
    labeled_at: datetime
    items: list[AnswerLabel]

    @model_validator(mode="after")
    def _check(self) -> Self:
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("Aynı soru iki kez etiketlenmiş")
        if self.source is LabelSource.JUDGE and not (self.judge_model and self.judge_prompt_sha256):
            raise ValueError("Judge etiketinde model ve prompt parmak izi zorunlu")
        if self.source is LabelSource.HUMAN and (self.judge_model or self.judge_prompt_sha256):
            raise ValueError("İnsan etiketinde judge alanları olmaz")
        return self

    def by_item(self) -> dict[str, AnswerLabel]:
        return {item.item_id: item for item in self.items}


class Sample(_Strict):
    """İnsan etiketlemesi için belgelenmiş örneklem: çerçeve, boyut ve tohumla yeniden üretilir."""

    schema_version: Literal[1] = SCHEMA_VERSION
    run_id: str
    split: Split | None
    seed: int
    # Örneklem çerçevesi: koşudaki hatasız cevaplanabilir sorular (reddedilenler dahil;
    # reddedilen cevap 0 puan sayılır ve tabloya girmez).
    frame_size: int
    item_ids: list[str]
    created_at: datetime


def load_labels(path: Path) -> LabelSet:
    return LabelSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_sample(path: Path) -> Sample:
    return Sample.model_validate_json(path.read_text(encoding="utf-8"))


# --- Örneklem ve kapsam ------------------------------------------------------------------------


def answerable_frame(record: RunRecord) -> list[ItemResult]:
    """Doğruluk paydasına giren sorular: hatasız cevaplanabilir sorular."""
    return [r for r in record.items if r.kind is ItemKind.ANSWERABLE and r.error is None]


def is_answered(result: ItemResult) -> bool:
    return not result.declined and bool(result.answer)


def draw_sample(record: RunRecord, size: int, seed: int, now: datetime | None = None) -> Sample:
    if size < 1:
        raise ValueError("Örneklem en az 1 soru olmalı")
    frame = sorted(r.id for r in answerable_frame(record))
    chosen = random.Random(seed).sample(frame, min(size, len(frame)))
    return Sample(
        run_id=record.run_id,
        split=record.config.split,
        seed=seed,
        frame_size=len(frame),
        item_ids=sorted(chosen),
        created_at=now or datetime.now(UTC),
    )


# --- Etiketleme tablosu ------------------------------------------------------------------------


def describe(locator: SourceLocator, titles: dict[str, str]) -> str:
    title = titles.get(locator.document_sha256, locator.document_sha256[:12])
    if locator.page is not None:
        return f"{title} s.{locator.page}"
    if locator.t_start is not None and locator.t_end is not None:
        return f"{title} {locator.t_start:.0f}–{locator.t_end:.0f} sn"
    return title


def document_titles(record: RunRecord) -> dict[str, str]:
    return {d.sha256: d.title for d in record.corpus.documents if d.sha256}


def passages_text(result: ItemResult, titles: dict[str, str]) -> str:
    """Getirilen pasajlar, cevaptaki sırayla: "[1] başlık s.3: metin"."""
    blocks = [
        f"[{n}] {describe(locator, titles)}: {text}"
        for n, (locator, text) in enumerate(
            zip(result.retrieved, result.retrieved_text, strict=False), start=1
        )
    ]
    return "\n\n".join(blocks)


def check_gold(record: RunRecord, gold_path: Path) -> GoldSet:
    if file_sha256(gold_path) != record.config.gold_set_sha256:
        raise ValueError("Gold set dosyası koşudakiyle aynı değil (SHA-256 farklı)")
    return load_gold_set(gold_path)


def sheet_rows(record: RunRecord, gold: GoldSet, item_ids: Sequence[str]) -> list[dict[str, str]]:
    references = {item.id: item.reference_answer or "" for item in gold.items}
    questions = {item.id: item.question for item in gold.items}
    titles = document_titles(record)
    wanted = set(item_ids)
    rows: list[dict[str, str]] = []
    for result in answerable_frame(record):
        if result.id not in wanted or not is_answered(result):
            continue
        base = dict.fromkeys(SHEET_COLUMNS, "") | {
            "run_id": record.run_id,
            "item_id": result.id,
        }
        rows.append(
            base
            | {
                "row": "answer",
                "question": questions.get(result.id, ""),
                "reference_answer": references.get(result.id, ""),
                "answer": result.answer or "",
                "passages": _fit_cell(passages_text(result, titles)),
            }
        )
        for index, claim in enumerate(split_claims(result.answer or "")):
            rows.append(
                base
                | {
                    "row": "claim",
                    "claim_index": str(index),
                    "claim_sha256": claim_sha256(claim),
                    "claim": claim,
                }
            )
    return rows


def _fit_cell(text: str) -> str:
    if len(text) <= _CELL_LIMIT:
        return text
    return text[:_CELL_LIMIT] + "\n[… pasaj metni tablo sınırında kesildi; devamı materyalde]"


def expected_claims(result: ItemResult) -> list[tuple[int, str]]:
    """Cevabın güncel iddiaları: (sıra, metin parmak izi)."""
    return [(i, claim_sha256(c)) for i, c in enumerate(split_claims(result.answer or ""))]


def claims_match(label: AnswerLabel, result: ItemResult) -> bool:
    """Etiketteki iddialar cevabın güncel iddialarıyla birebir aynı mı (sıra + parmak izi)?"""
    return [(c.index, c.claim_sha256) for c in label.claims] == expected_claims(result)


def write_sheet(rows: Sequence[dict[str, str]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig + ";" Türkçe Excel'de sütunlar doğru açılsın diye.
    with path.open("x", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SHEET_COLUMNS, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def read_sheet(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    header = text.split("\n", 1)[0]
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    reader = csv.DictReader(text.splitlines(keepends=True), delimiter=delimiter)
    missing = set(SHEET_COLUMNS) - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"Tabloda eksik sütun: {', '.join(sorted(missing))}")
    return [{k: (v or "").strip() for k, v in row.items() if k} for row in reader]


def _parse_score(value: str) -> int | None:
    try:
        number = float(value.replace(",", "."))
    except ValueError:
        return None
    return int(number) if number in (0, 1, 2) else None


def labels_from_sheet(
    record: RunRecord,
    rows: Sequence[dict[str, str]],
    rater: str,
    expected_ids: Collection[str] | None = None,
    now: datetime | None = None,
) -> LabelSet:
    """Doldurulmuş tabloyu doğrular ve metinsiz etiket kümesine çevirir.

    `expected_ids` (örneklem) verilirse oradaki her cevaplanmış soru tabloda olmalı, dışındaki
    soru olmamalı. Eksik, yinelenen ya da geçersiz hücre varsa hepsi birlikte listelenir
    (ValueError); yarım tablo sessizce kabul edilmez.
    """
    results = {r.id: r for r in answerable_frame(record)}
    problems: list[str] = []
    scores: dict[str, int] = {}
    bad_scores: set[str] = set()
    claims: dict[str, list[ClaimLabel]] = {}
    for number, row in enumerate(rows, start=2):
        item_id = row["item_id"]
        where = f"satır {number} ({item_id})"
        if row["run_id"] != record.run_id:
            problems.append(f"{where}: başka bir koşunun tablosu ({row['run_id']})")
            continue
        result = results.get(item_id)
        if result is None or not is_answered(result):
            problems.append(f"{where}: koşuda cevaplanmış böyle bir soru yok")
            continue
        if expected_ids is not None and item_id not in expected_ids:
            problems.append(f"{where}: soru örneklemde yok")
            continue
        if row["row"] == "answer":
            score = _parse_score(row["score"])
            if item_id in scores or item_id in bad_scores:
                problems.append(f"{where}: aynı sorunun ikinci cevap satırı")
            elif score is None:
                bad_scores.add(item_id)
                problems.append(f"{where}: puan 0, 1 ya da 2 olmalı ('{row['score']}')")
            else:
                scores[item_id] = score
        elif row["row"] == "claim":
            expected = split_claims(result.answer or "")
            try:
                index = int(row["claim_index"])
            except ValueError:
                problems.append(f"{where}: iddia sırası okunamadı")
                continue
            if index >= len(expected) or claim_sha256(expected[index]) != row["claim_sha256"]:
                problems.append(f"{where}: iddia bu koşunun cevabıyla uyuşmuyor")
                continue
            if any(c.index == index for c in claims.get(item_id, [])):
                problems.append(f"{where}: aynı iddianın ikinci satırı")
                continue
            verdict = _VERDICTS.get(row["label"].casefold())
            if verdict is None:
                problems.append(f"{where}: etiket supported ya da unsupported olmalı")
                continue
            claims.setdefault(item_id, []).append(
                ClaimLabel(index=index, claim_sha256=row["claim_sha256"], label=verdict)
            )
        else:
            problems.append(f"{where}: bilinmeyen satır türü '{row['row']}'")
    for item_id in sorted(set(scores) | set(claims)):
        expected = len(split_claims(results[item_id].answer or ""))
        if len(claims.get(item_id, [])) != expected:
            problems.append(f"{item_id}: {expected} iddianın hepsi etiketlenmemiş")
        if item_id not in scores and item_id not in bad_scores:
            problems.append(f"{item_id}: cevap puanı yok")
    if expected_ids is not None:
        seen = set(scores) | set(claims) | bad_scores
        for item_id in sorted(expected_ids):
            result = results.get(item_id)
            if result is not None and is_answered(result) and item_id not in seen:
                problems.append(f"{item_id}: örneklemdeki soru tabloda yok")
    if problems:
        raise ValueError("Tablo eksik ya da hatalı:\n  " + "\n  ".join(problems))
    return LabelSet(
        run_id=record.run_id,
        source=LabelSource.HUMAN,
        rater=rater,
        labeled_at=now or datetime.now(UTC),
        items=[
            AnswerLabel(
                item_id=item_id,
                score=scores[item_id],
                claims=sorted(claims.get(item_id, []), key=lambda c: c.index),
            )
            for item_id in sorted(scores)
        ],
    )


# --- Komut satırı ------------------------------------------------------------------------------


def _write_json(model: _Strict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # "x": var olan etiket dosyasının üzerine yazılmaz; düzeltme için dosya bilerek silinir.
    with path.open("x", encoding="utf-8") as file:
        file.write(model.model_dump_json(indent=2))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.labels", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    sample = commands.add_parser("sample", help="Belgelenmiş örneklem")
    sample.add_argument("--run", type=Path, required=True)
    sample.add_argument("--size", type=int, default=40)
    sample.add_argument("--seed", type=int, required=True)
    sample.add_argument("--labels-root", type=Path, default=Path("human_labels"))

    sheet = commands.add_parser("sheet", help="Boş etiketleme tablosu")
    sheet.add_argument("--run", type=Path, required=True)
    sheet.add_argument("--gold", type=Path, required=True)
    sheet.add_argument("--sample", type=Path, help="Varsayılan: human_labels/<run_id>/sample.json")
    sheet.add_argument("--labels-root", type=Path, default=Path("human_labels"))
    sheet.add_argument("--out", type=Path, help="Varsayılan: runs/<run_id>.sheet.csv")

    imp = commands.add_parser("import", help="Doldurulmuş tabloyu etiket dosyasına çevir")
    imp.add_argument("--run", type=Path, required=True)
    imp.add_argument("--sheet", type=Path, required=True)
    imp.add_argument("--rater", required=True, help="Takma ad, ör. rater-a")
    imp.add_argument("--labels-root", type=Path, default=Path("human_labels"))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    # Windows konsolu (cp1254) Türkçe karakterleri bozmasın.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    record = load_run(args.run)
    folder = args.labels_root / record.run_id
    if args.command == "sample":
        sample = draw_sample(record, args.size, args.seed)
        _write_json(sample, folder / "sample.json")
        print(
            f"Örneklem: {len(sample.item_ids)}/{sample.frame_size} soru → {folder / 'sample.json'}"
        )
    elif args.command == "sheet":
        sample = load_sample(args.sample or folder / "sample.json")
        if sample.run_id != record.run_id:
            raise SystemExit("Örneklem başka bir koşuya ait")
        rows = sheet_rows(record, check_gold(record, args.gold), sample.item_ids)
        out = args.out or args.run.with_suffix(".sheet.csv")
        write_sheet(rows, out)
        print(f"Etiketleme tablosu ({len(rows)} satır, git'e girmez): {out}")
    else:
        sample = load_sample(folder / "sample.json")
        if sample.run_id != record.run_id:
            raise SystemExit("Örneklem başka bir koşuya ait")
        try:
            labels = labels_from_sheet(
                record, read_sheet(args.sheet), args.rater, expected_ids=sample.item_ids
            )
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        _write_json(labels, folder / f"{labels.rater}.json")
        print(f"{len(labels.items)} cevabın etiketi → {folder / f'{labels.rater}.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
