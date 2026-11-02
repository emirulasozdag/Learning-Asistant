"""Video-zaman önceliğinin katkısı (#19): aynı sorular, öncelikli ve önceliksiz arama (LLM yok).

Kullanım (evaluation/ içinden, backend kurulu ve veritabanı açıkken):

    python -m harness.time_prior --gold gold_sets/BLM2512/gold_set.json \
        --split calibration --files-root .. --out runs/

Yalnızca oynatma konumu (`playback`) ve kanıtı olan cevaplanabilir sorular koşulur. Her soru,
önceliksiz (video gönderilmez) ve pencere × ağırlık değişkeleriyle aranır. Raporlanan:
- Recall@5 ve ilk doğru parçanın sırası, değişke başına.
- Önceliksize göre iyileşen / kötüleşen / değişmeyen soru sayısı.
- Ders (oynatılan video) başına Recall@5: öncelik birden çok derste ayrı ayrı doğrulanır.
- Kanıtın oynatma anına göre yeri: aynı videoda pencere içinde, aynı videoda uzakta, başka bir
  dokümanda. Öncelik "başka doküman" kanıtını (slayt, ders notu) aşağı itmemelidir.

Değişke yalnızca `--split calibration` koşusunda önerilir; held-out mevcut ayarı raporlar.
Çıktı `<out>/<id>.json` ve `.md`; var olan dosyanın üzerine yazılmaz.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from harness.retrieval_sweep import first_hit_rank
from harness.run import RECALL_K, git_state, select_items
from harness.schemas import GoldItem, ItemKind, Split, load_gold_set, load_manifest
from harness.validate import structural_errors

NO_PRIOR = "öncelik yok"
WINDOWS_S = (60.0, 120.0, 240.0)
WEIGHTS = (0.25, 0.5, 1.0)
# İlk doğru parçanın sırası bu derinliğe kadar aranır (Recall@5'in dışındaki kayma da görünür).
RANK_DEPTH = 50
# Bundan az sorusu olan dersin sonucu "küçük örnek" olarak işaretlenir.
MIN_ITEMS_PER_LECTURE = 10


class Relation(StrEnum):
    """Gold kanıtının oynatma anına göre yeri."""

    NEAR = "aynı video, pencere içinde"
    FAR = "aynı video, pencere dışında"
    OTHER = "başka doküman"


@dataclass(frozen=True)
class Variant:
    name: str
    window_s: float | None = None
    weight: float | None = None

    @property
    def uses_prior(self) -> bool:
        return self.window_s is not None and self.weight is not None


@dataclass
class VariantResult:
    name: str
    window_s: float | None
    weight: float | None
    recall_at_5: float | None
    by_lecture: dict[str, float | None]
    by_relation: dict[str, float | None]
    improved: int
    worsened: int
    unchanged: int
    per_item_rank: dict[str, int | None] = field(default_factory=dict)


def variants(production_window_s: float, production_weight: float) -> list[Variant]:
    """Önceliksiz taban + pencere × ağırlık ızgarası; üretim ayarı adında işaretlenir."""
    result = [Variant(NO_PRIOR)]
    for window in WINDOWS_S:
        for weight in WEIGHTS:
            production = (window, weight) == (production_window_s, production_weight)
            label = f"pencere {window:g} sn, ağırlık {weight:g}" + (
                " (üretim)" if production else ""
            )
            result.append(Variant(label, window, weight))
    if not any(v.window_s == production_window_s and v.weight == production_weight for v in result):
        result.append(
            Variant(
                f"pencere {production_window_s:g} sn, ağırlık {production_weight:g} (üretim)",
                production_window_s,
                production_weight,
            )
        )
    return result


def playback_items(items: Sequence[GoldItem]) -> list[GoldItem]:
    return [
        item
        for item in items
        if item.kind is ItemKind.ANSWERABLE and item.evidence and item.playback is not None
    ]


def relation(item: GoldItem, window_s: float) -> Relation:
    """Kanıtın en yakın yeri: herhangi bir kanıt pencere içindeyse NEAR."""
    assert item.playback is not None
    playback = item.playback
    same_video = [e for e in item.evidence if e.document_sha256 == playback.document_sha256]
    if not same_video:
        return Relation.OTHER
    for evidence in same_video:
        if evidence.t_start is None or evidence.t_end is None:
            return Relation.NEAR  # Videonun tamamı kanıt.
        if evidence.t_start <= playback.time_s + window_s and (
            playback.time_s - window_s <= evidence.t_end
        ):
            return Relation.NEAR
    return Relation.FAR


def summarize(
    variant: Variant,
    items: Sequence[GoldItem],
    ranks: dict[str, int | None],
    baseline: dict[str, int | None] | None,
    relation_window_s: float,
) -> VariantResult:
    """Değişkenin sıralarından Recall@5, ders/kanıt yeri kırılımı ve tabana göre fark."""

    def recall(subset: Sequence[GoldItem]) -> float | None:
        if not subset:
            return None
        hits = sum(1 for i in subset if (r := ranks[i.id]) is not None and r <= RECALL_K)
        return round(hits / len(subset), 4)

    lectures: dict[str, list[GoldItem]] = {}
    relations: dict[str, list[GoldItem]] = {r.value: [] for r in Relation}
    for item in items:
        assert item.playback is not None
        lectures.setdefault(item.playback.document_sha256, []).append(item)
        relations[relation(item, relation_window_s).value].append(item)

    improved = worsened = unchanged = 0
    for item in items if baseline is not None else []:
        before, after = _sort_key(baseline[item.id]), _sort_key(ranks[item.id])
        if after < before:
            improved += 1
        elif after > before:
            worsened += 1
        else:
            unchanged += 1
    return VariantResult(
        name=variant.name,
        window_s=variant.window_s,
        weight=variant.weight,
        recall_at_5=recall(items),
        by_lecture={sha: recall(group) for sha, group in sorted(lectures.items())},
        by_relation={name: recall(group) for name, group in relations.items()},
        improved=improved,
        worsened=worsened,
        unchanged=unchanged,
        per_item_rank=dict(ranks),
    )


def _sort_key(rank: int | None) -> float:
    return float("inf") if rank is None else rank


def recommend(results: Sequence[VariantResult]) -> VariantResult | None:
    """En yüksek Recall@5 veren öncelikli değişke; başka doküman kanıtı tabandan kötü olmamalı.

    Eşitlikte daha az kötüleşen soru, sonra daha küçük ağırlık ve pencere (daha az müdahale).
    Hiçbir değişke tabanı geçmiyorsa None: öncelik bu sorularda katkı göstermedi.
    """
    baseline = next((r for r in results if r.window_s is None), None)
    if baseline is None or baseline.recall_at_5 is None:
        return None
    other = Relation.OTHER.value

    def safe(result: VariantResult) -> bool:
        before, after = baseline.by_relation.get(other), result.by_relation.get(other)
        return before is None or (after is not None and after >= before)

    candidates = [
        r
        for r in results
        if r.window_s is not None
        and r.recall_at_5 is not None
        and r.recall_at_5 > baseline.recall_at_5
        and safe(r)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: (-r.recall_at_5, r.worsened, r.weight, r.window_s))


def coverage_gaps(items: Sequence[GoldItem], all_items: Sequence[GoldItem]) -> list[str]:
    """Doğrulamayı geçersiz ya da zayıf kılan eksikler; sentetik değerle doldurulmaz."""
    gaps = []
    answerable = [i for i in all_items if i.kind is ItemKind.ANSWERABLE and i.evidence]
    if not items:
        gaps.append(
            "Oynatma konumu ve kanıtı olan soru yok: zaman önceliğinin katkısı ölçülemedi "
            "(gold sete `playback` eklenmeli, #18)."
        )
        return gaps
    if len(items) < len(answerable):
        gaps.append(
            f"{len(answerable) - len(items)} kanıtlı soruda oynatma konumu yok; "
            "bu sorular karşılaştırmaya girmedi."
        )
    lectures: dict[str, int] = {}
    for item in items:
        assert item.playback is not None
        lectures[item.playback.document_sha256] = lectures.get(item.playback.document_sha256, 0) + 1
    if len(lectures) < 2:
        gaps.append(
            "Oynatma konumları tek bir derse (videoya) ait: birden çok derste doğrulama yapılamadı."
        )
    small = [sha[:12] for sha, count in sorted(lectures.items()) if count < MIN_ITEMS_PER_LECTURE]
    if small:
        gaps.append(
            f"{len(small)} derste {MIN_ITEMS_PER_LECTURE}'dan az soru var (küçük örnek): "
            + ", ".join(small)
        )
    return gaps


# --- Gerçek hat (veritabanı + backend) ---------------------------------------------------------


def compare_variants(
    db, course, items: Sequence[GoldItem], videos: dict[str, int], locate, embedder
) -> list[VariantResult]:
    """Her değişkede aynı soruları arar; ilk sonuç önceliksiz tabandır.

    `videos`: oynatılan videonun SHA-256'sı → doküman kimliği; `locate`: chunk id → konum.
    """
    from app.retrieval.hybrid import RetrievalParams, retrieve
    from app.retrieval.types import VideoPosition

    production = RetrievalParams()
    results: list[VariantResult] = []
    baseline: dict[str, int | None] | None = None
    for variant in variants(production.video_window_s, production.video_weight):
        params = (
            RetrievalParams(video_window_s=variant.window_s, video_weight=variant.weight)
            if variant.uses_prior
            else production
        )
        ranks: dict[str, int | None] = {}
        for item in items:
            assert item.playback is not None
            video = (
                VideoPosition(videos[item.playback.document_sha256], item.playback.time_s)
                if variant.uses_prior
                else None
            )
            result = retrieve(
                db,
                course,
                item.question,
                video=video,
                k=RANK_DEPTH,
                embedder=embedder,
                params=params,
            )
            ranks[item.id] = first_hit_rank(
                [locate(p.source_id) for p in result.passages], item.evidence
            )
        results.append(summarize(variant, items, ranks, baseline, production.video_window_s))
        if baseline is None:
            baseline = ranks
    return results


def run_comparison(args: argparse.Namespace) -> dict:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.retrieval.hybrid import RetrievalParams
    from app.retrieval.index import inventory
    from harness.corpus import Locator, find_course
    from harness.retrieval_sweep import _cached_embedder
    from harness.run import playback_documents

    split = None if args.split == "all" else Split(args.split)
    gold = load_gold_set(args.gold)
    manifest = load_manifest(args.manifest or args.gold.parent / gold.manifest)
    errors = structural_errors(gold, manifest)
    if errors:
        raise SystemExit("Gold set tutarsız:\n  " + "\n  ".join(errors))
    selected, gaps = select_items(gold.items, split, args.include_unreviewed)
    items = playback_items(selected)
    gaps += coverage_gaps(items, selected)
    production = RetrievalParams()
    embedder = _cached_embedder()
    engine = create_engine(args.database_url or settings.database_url)

    with Session(engine) as db:
        course = find_course(db, gold.course_code)
        locator = Locator(db, args.files_root)
        index = inventory(db, course.id)
        videos = playback_documents(db, course, locator)
        missing = sorted(
            {
                i.playback.document_sha256[:12]
                for i in items
                if i.playback.document_sha256 not in videos
            }
        )
        if missing:
            gaps.append(f"Oynatılan video indekste yok (soru koşulmadı): {', '.join(missing)}")
            items = [i for i in items if i.playback.document_sha256 in videos]

        results = compare_variants(db, course, items, videos, locator.locate, embedder)
        db.rollback()

    calibrating = split is Split.CALIBRATION
    commit, dirty = git_state(args.repo)
    recommended = recommend(results) if calibrating else None
    return {
        "comparison_id": (
            f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}_time_prior_{args.split}_{uuid.uuid4().hex[:6]}"
        ),
        "split": args.split,
        "git_commit": commit,
        "git_dirty": dirty,
        "gold_set": str(args.gold),
        "embedding_identity": embedder.identity,
        "index_fingerprint": index.fingerprint,
        "production": {
            "video_window_s": production.video_window_s,
            "video_weight": production.video_weight,
        },
        "relation_window_s": production.video_window_s,
        "questions": {"with_playback": len(items), "selected": len(selected)},
        "lectures": sorted({i.playback.document_sha256 for i in items}),
        "variants": [asdict(r) for r in results],
        "recommended": asdict(recommended) if recommended else None,
        "gaps": gaps,
    }


def render_markdown(report: dict) -> str:
    def pct(value):
        return "—" if value is None else f"{value:.2f}"

    lectures = report["lectures"]
    lines = [
        f"# Video-zaman önceliği `{report['comparison_id']}`",
        "",
        f"- Split: `{report['split']}` · commit: `{(report['git_commit'] or '?')[:8]}`"
        + (" (commit'lenmemiş değişiklik var)" if report["git_dirty"] else ""),
        f"- Embedding: `{report['embedding_identity']}` · "
        f"indeks: `{report['index_fingerprint'][:16]}`",
        f"- Oynatma konumlu soru: {report['questions']['with_playback']} "
        f"(seçilen {report['questions']['selected']}), ders (video): {len(lectures)}",
        f"- Üretim ayarı: pencere {report['production']['video_window_s']:g} sn, "
        f"ağırlık {report['production']['video_weight']:g}",
        "",
        "## Değişkeler",
        "",
        "| Değişke | Recall@5 | İyileşen | Kötüleşen | Aynı | "
        + " | ".join(r.value for r in Relation)
        + " |",
        "|---" * (5 + len(Relation)) + "|",
    ]
    for v in report["variants"]:
        lines.append(
            f"| {v['name']} | {pct(v['recall_at_5'])} | {v['improved']} | {v['worsened']} "
            f"| {v['unchanged']} | "
            + " | ".join(pct(v["by_relation"].get(r.value)) for r in Relation)
            + " |"
        )
    lines += [
        "",
        f"Kanıt yeri, üretim penceresine (±{report['relation_window_s']:g} sn) göre hesaplanır. "
        "İyileşen/kötüleşen: ilk doğru parçanın sırası önceliksize göre.",
    ]
    if lectures:
        lines += [
            "",
            "## Ders başına Recall@5",
            "",
            "| Değişke | " + " | ".join(f"`{sha[:12]}`" for sha in lectures) + " |",
            "|---" * (len(lectures) + 1) + "|",
        ]
        for v in report["variants"]:
            lines.append(
                f"| {v['name']} | "
                + " | ".join(pct(v["by_lecture"].get(sha)) for sha in lectures)
                + " |"
            )
    if report["recommended"]:
        r = report["recommended"]
        lines += [
            "",
            f"Kalibrasyon önerisi: {r['name']} (Recall@5 {pct(r['recall_at_5'])}, "
            f"kötüleşen {r['worsened']}).",
        ]
    elif report["split"] == Split.CALIBRATION:
        lines += [
            "",
            "Kalibrasyon önerisi yok: hiçbir değişke önceliksiz aramayı geçmedi.",
        ]
    else:
        lines += ["", "Held-out: ayar seçmek için kullanılmaz, yalnızca rapor."]
    if report["gaps"]:
        lines += ["", "## Boşluklar", ""] + [f"- {gap}" for gap in report["gaps"]]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.time_prior", description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--split", choices=[s.value for s in Split] + ["all"], required=True)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    parser.add_argument("--files-root", type=Path, default=Path(".."))
    parser.add_argument("--repo", type=Path, default=Path(".."))
    parser.add_argument("--database-url")
    parser.add_argument("--include-unreviewed", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    report = run_comparison(args)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{report['comparison_id']}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    with path.with_suffix(".md").open("x", encoding="utf-8") as file:
        file.write(render_markdown(report))
    print(f"Karşılaştırma: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
