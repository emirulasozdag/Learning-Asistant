"""Arama karşılaştırması ve alakasızlık kapısı kalibrasyonu (LLM çağrılmaz).

Kullanım (evaluation/ içinden, backend kurulu ve veritabanı açıkken):

    python -m harness.retrieval_sweep --gold gold_sets/BLM2512/gold_set.json \
        --split calibration --files-root .. --out runs/ [--follow-ups takip.json]

Yapılanlar:
- Yöntemler (yalnız anlamsal, yalnız kelime, hibrit RRF, aday sayısı ve RRF k değişkeleri)
  aynı sorularda Recall@5 ve aday recall'u (birleştirilmiş tüm adaylar) ile karşılaştırılır.
- Kapı eşikleri (anlamsal benzerlik × anahtar kelime kapsaması) ızgarada denenir: aşırı
  reddetme (cevaplanabilir soru reddedildi) ve kapsam dışı reddetme oranı.
- Eşik yalnızca `--split calibration` koşusunda önerilir; held-out koşusu mevcut ayarı raporlar.
- `--follow-ups`: takip sorusu denemeleri, JSON listesi
  `[{"previous": "...", "question": "...", "expect": "admit" | "decline"}]` (geliştirme amaçlı;
  gold set şemasında sohbet bağlamı yok).

Çıktı `<out>/<sweep_id>.json` ve `.md`; var olan dosyanın üzerine yazılmaz.
"""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from harness.metrics import retrieval as retrieval_metrics
from harness.metrics import scope
from harness.run import RECALL_K, git_state, select_items
from harness.schemas import ItemKind, SourceLocator, Split, load_gold_set, load_manifest
from harness.validate import structural_errors

SIMILARITY_GRID = [round(0.70 + 0.01 * i, 2) for i in range(17)]  # 0.70 … 0.86
# 1.01: kelime kapsaması kapalı (yalnızca anlamsal benzerlik karar verir).
COVERAGE_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.01]
FOLLOW_UP_GRID = [round(0.70 + 0.01 * i, 2) for i in range(13)]  # 0.70 … 0.82


@dataclass
class ItemSignals:
    id: str
    kind: str
    best_similarity: float | None
    keyword_coverage: float | None


@dataclass
class VariantResult:
    name: str
    params: dict
    recall_at_5: float | None
    candidate_recall: float | None
    candidates_mean: float
    per_item_rank: dict[str, int | None] = field(default_factory=dict)


@dataclass
class GateCell:
    min_similarity: float
    min_keyword_coverage: float
    over_refusal: float | None
    out_of_scope_decline: float | None


def variants():
    from app.retrieval.hybrid import DENSE, LEXICAL, RetrievalParams

    return [
        ("hibrit (üretim)", RetrievalParams()),
        ("yalnız anlamsal", RetrievalParams(methods=(DENSE,))),
        ("yalnız kelime", RetrievalParams(methods=(LEXICAL,))),
        ("hibrit, aday 5", RetrievalParams(candidates_per_method=5)),
        ("hibrit, aday 20", RetrievalParams(candidates_per_method=20)),
        ("hibrit, rrf_k 20", RetrievalParams(rrf_k=20)),
    ]


def gate_passes(signals: ItemSignals, min_similarity: float, min_coverage: float) -> bool:
    """`hybrid._Signals.relevant` ile aynı kural (bağlamsız)."""
    by_meaning = signals.best_similarity is not None and signals.best_similarity >= min_similarity
    by_keywords = signals.keyword_coverage is not None and signals.keyword_coverage >= min_coverage
    return by_meaning or by_keywords


def gate_grid(signals: Sequence[ItemSignals]) -> list[GateCell]:
    answerable = [s for s in signals if s.kind == ItemKind.ANSWERABLE]
    out_of_scope = [s for s in signals if s.kind == ItemKind.OUT_OF_SCOPE]
    cells = []
    for similarity in SIMILARITY_GRID:
        for coverage in COVERAGE_GRID:
            refused = [not gate_passes(s, similarity, coverage) for s in answerable]
            declined = [not gate_passes(s, similarity, coverage) for s in out_of_scope]
            cells.append(
                GateCell(
                    similarity,
                    coverage,
                    scope.over_refusal_rate(refused) if refused else None,
                    scope.decline_rate(declined) if declined else None,
                )
            )
    return cells


def recommend(cells: Sequence[GateCell]) -> GateCell | None:
    """Aşırı reddetme hedefin altında kalan hücreler arasında en yüksek kapsam dışı reddetme.

    Eşitlikte daha az aşırı reddetme, sonra daha düşük (daha az iddialı) eşikler seçilir.
    """
    feasible = [
        c
        for c in cells
        if c.over_refusal is not None
        and c.out_of_scope_decline is not None
        and c.over_refusal <= scope.TARGET_OVER_REFUSAL_MAX
    ]
    if not feasible:
        return None
    return min(
        feasible,
        key=lambda c: (
            -c.out_of_scope_decline,
            c.over_refusal,
            c.min_similarity,
            c.min_keyword_coverage,
        ),
    )


def first_hit_rank(
    hits: Sequence[SourceLocator | None], evidence: Sequence[SourceLocator]
) -> int | None:
    for rank, hit in enumerate(hits, start=1):
        if hit is not None and any(gold.matches(hit) for gold in evidence):
            return rank
    return None


# --- Gerçek hat (veritabanı + backend) ---------------------------------------------------------


def _cached_embedder():
    from app.embeddings.provider import get_embedder

    base = get_embedder()

    class Cached:
        name = base.name
        dim = base.dim
        identity = base.identity

        @staticmethod
        @lru_cache(maxsize=4096)
        def _query(text: str) -> tuple[float, ...]:
            return tuple(base.embed_query(text))

        def embed_query(self, text: str) -> list[float]:
            return list(self._query(text))

        def embed_passages(self, texts: list[str]) -> list[list[float]]:
            return base.embed_passages(texts)

    return Cached()


def run_sweep(args: argparse.Namespace) -> dict:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.retrieval.hybrid import RetrievalParams, retrieve
    from app.retrieval.index import inventory
    from harness.corpus import Locator, find_course

    split = None if args.split == "all" else Split(args.split)
    gold = load_gold_set(args.gold)
    manifest = load_manifest(args.manifest or args.gold.parent / gold.manifest)
    errors = structural_errors(gold, manifest)
    if errors:
        raise SystemExit("Gold set tutarsız:\n  " + "\n  ".join(errors))
    items, gaps = select_items(gold.items, split, args.include_unreviewed)
    answerable = [i for i in items if i.kind is ItemKind.ANSWERABLE and i.evidence]
    embedder = _cached_embedder()
    engine = create_engine(args.database_url or settings.database_url)

    with Session(engine) as db:
        course = find_course(db, gold.course_code)
        locator = Locator(db, args.files_root)
        index = inventory(db, course.id)
        if index.stale(embedder.identity):
            gaps.append(
                f"{index.stale(embedder.identity)} parça etkin embedder'la vektörleştirilmemiş; "
                "anlamsal arama bunları görmez (python -m app.scripts.reembed)"
            )

        unresolved = 0
        results = []
        for name, params in variants():
            top, candidates, ranks, counts = [], [], {}, []
            for item in answerable:
                wide = retrieve(db, course, item.question, embedder=embedder, k=1000, params=params)
                # Sıra korunur: konumu çözülemeyen aday eşleşmez ama yerini tutar.
                located = [locator.locate(p.source_id) for p in wide.passages]
                unresolved += located.count(None)
                counts.append(len(located))
                top.append(located[:RECALL_K])
                candidates.append(located)
                ranks[item.id] = first_hit_rank(located, item.evidence)
            evidence = [i.evidence for i in answerable]
            results.append(
                VariantResult(
                    name=name,
                    params=asdict(params),
                    recall_at_5=_recall(top, evidence, RECALL_K),
                    candidate_recall=_recall(candidates, evidence, 1000),
                    candidates_mean=sum(counts) / len(counts) if counts else 0.0,
                    per_item_rank=ranks,
                )
            )

        if unresolved:
            gaps.append(f"{unresolved} adayın kaynak konumu çözülemedi (eşleşmeyen sayıldı)")
        signals = []
        for item in items:
            result = retrieve(db, course, item.question, embedder=embedder)
            signals.append(
                ItemSignals(
                    item.id, item.kind.value, result.best_similarity, result.keyword_coverage
                )
            )

        follow_ups = []
        if args.follow_ups:
            probes = json.loads(args.follow_ups.read_text(encoding="utf-8"))
            for probe in probes:
                alone = retrieve(db, course, probe["question"], embedder=embedder)
                with_context = retrieve(
                    db, course, probe["question"], embedder=embedder, context=probe["previous"]
                )
                follow_ups.append(
                    {
                        **probe,
                        "alone_similarity": alone.best_similarity,
                        "alone_coverage": alone.keyword_coverage,
                        "alone_relevant": alone.relevant,
                        "context_relevant_without_floor": retrieve(
                            db,
                            course,
                            probe["question"],
                            embedder=embedder,
                            context=probe["previous"],
                            params=RetrievalParams(follow_up_min_similarity=0.0),
                        ).relevant,
                        "admitted": with_context.relevant,
                    }
                )
        db.rollback()

    # Izgaralar yalnızca kalibrasyonda: held-out'tan eşik seçilmesin, sabit ayar raporlanır.
    calibrating = split is Split.CALIBRATION
    cells = gate_grid(signals) if calibrating else []
    commit, dirty = git_state(args.repo)
    current = RetrievalParams().resolved()
    return {
        "sweep_id": f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}_sweep_{args.split}_{uuid.uuid4().hex[:6]}",
        "split": args.split,
        "git_commit": commit,
        "git_dirty": dirty,
        "gold_set": str(args.gold),
        "embedding_identity": embedder.identity,
        "index_fingerprint": index.fingerprint,
        "index_by_embedding": {str(k): v for k, v in index.by_embedding.items()},
        "current": asdict(current),
        "questions": {"answerable_with_evidence": len(answerable), "all": len(items)},
        "variants": [asdict(r) for r in results],
        "signals": [asdict(s) for s in signals],
        "gate_grid": [asdict(c) for c in cells],
        "gate_current": asdict(_cell_at(signals, current)),
        "gate_recommended": asdict(r) if calibrating and (r := recommend(cells)) else None,
        "follow_ups": follow_ups,
        "follow_up_grid": _follow_up_grid(follow_ups) if calibrating else [],
        "gaps": gaps,
    }


def _recall(hits, evidence, k) -> float | None:
    if not evidence:
        return None

    def match(gold: SourceLocator, hit: SourceLocator | None) -> bool:
        return hit is not None and gold.matches(hit)

    return round(retrieval_metrics.recall_at_k(hits, evidence, k=k, match=match), 4)


def _cell_at(signals: Sequence[ItemSignals], params) -> GateCell:
    answerable = [s for s in signals if s.kind == ItemKind.ANSWERABLE]
    out_of_scope = [s for s in signals if s.kind == ItemKind.OUT_OF_SCOPE]
    sim, cov = params.min_similarity, params.min_keyword_coverage
    refused = [not gate_passes(s, sim, cov) for s in answerable]
    declined = [not gate_passes(s, sim, cov) for s in out_of_scope]
    return GateCell(
        sim,
        cov,
        scope.over_refusal_rate(refused) if refused else None,
        scope.decline_rate(declined) if declined else None,
    )


def _follow_up_grid(follow_ups: Sequence[dict]) -> list[dict]:
    """Takip tabanı (yeni sorunun kendi benzerliği) için doğru karar oranı."""
    rows = []
    for floor in FOLLOW_UP_GRID if follow_ups else []:
        correct = 0
        for probe in follow_ups:
            admitted = probe["alone_relevant"] or (
                probe["context_relevant_without_floor"]
                and (probe["alone_similarity"] or 0.0) >= floor
            )
            correct += admitted == (probe["expect"] == "admit")
        rows.append({"floor": floor, "correct": correct, "total": len(follow_ups)})
    return rows


def render_markdown(sweep: dict) -> str:
    def pct(value):
        return "—" if value is None else f"{value:.2f}"

    lines = [
        f"# Arama karşılaştırması `{sweep['sweep_id']}`",
        "",
        f"- Split: `{sweep['split']}` · commit: `{(sweep['git_commit'] or '?')[:8]}`"
        + (" (commit'lenmemiş değişiklik var)" if sweep["git_dirty"] else ""),
        f"- Embedding: `{sweep['embedding_identity']}` · "
        f"indeks: `{sweep['index_fingerprint'][:16]}`",
        f"- Soru: {sweep['questions']['all']} (kanıtlı cevaplanabilir "
        f"{sweep['questions']['answerable_with_evidence']})",
        "",
        "## Yöntemler",
        "",
        "| Değişke | Recall@5 | Aday recall | Ort. aday |",
        "|---|---|---|---|",
    ]
    for v in sweep["variants"]:
        lines.append(
            f"| {v['name']} | {pct(v['recall_at_5'])} | {pct(v['candidate_recall'])} "
            f"| {v['candidates_mean']:.1f} |"
        )
    lines += ["", "İlk doğru parçanın sırası (— = adaylarda yok):", ""]
    names = [v["name"] for v in sweep["variants"]]
    lines.append("| Soru | " + " | ".join(names) + " |")
    lines.append("|---" * (len(names) + 1) + "|")
    for item_id in sweep["variants"][0]["per_item_rank"]:
        ranks = [v["per_item_rank"][item_id] for v in sweep["variants"]]
        lines.append(
            f"| {item_id} | " + " | ".join("—" if r is None else str(r) for r in ranks) + " |"
        )

    current = sweep["gate_current"]
    lines += [
        "",
        "## Alakasızlık kapısı",
        "",
        f"Mevcut ayar: benzerlik ≥ {current['min_similarity']} ya da kapsama ≥ "
        f"{current['min_keyword_coverage']} → aşırı reddetme {pct(current['over_refusal'])}, "
        f"kapsam dışı reddetme {pct(current['out_of_scope_decline'])}",
    ]
    if sweep["gate_recommended"]:
        r = sweep["gate_recommended"]
        lines.append(
            f"Kalibrasyon önerisi: benzerlik ≥ {r['min_similarity']}, kapsama ≥ "
            f"{r['min_keyword_coverage']} → aşırı reddetme {pct(r['over_refusal'])}, "
            f"kapsam dışı reddetme {pct(r['out_of_scope_decline'])}"
        )
    elif sweep["split"] != Split.CALIBRATION:
        lines.append("Held-out: eşik seçmek için kullanılmaz, yalnızca rapor.")
    coverages = sorted({c["min_keyword_coverage"] for c in sweep["gate_grid"]})
    lines += (
        []
        if not coverages
        else [
            "",
            "Hücre: aşırı reddetme / kapsam dışı reddetme. Sütun: kapsama eşiği (1.01 = kapalı).",
            "",
            "| benzerlik | " + " | ".join(str(c) for c in coverages) + " |",
            "|---" * (len(coverages) + 1) + "|",
        ]
    )
    by_similarity: dict[float, list[dict]] = {}
    for cell in sweep["gate_grid"]:
        by_similarity.setdefault(cell["min_similarity"], []).append(cell)
    for similarity, cells in by_similarity.items():
        row = sorted(cells, key=lambda c: c["min_keyword_coverage"])
        lines.append(
            f"| {similarity} | "
            + " | ".join(
                f"{pct(c['over_refusal'])} / {pct(c['out_of_scope_decline'])}" for c in row
            )
            + " |"
        )
    lines += [
        "",
        "Soru sinyalleri:",
        "",
        "| Soru | Tür | Benzerlik | Kapsama |",
        "|---|---|---|---|",
    ]
    for s in sweep["signals"]:
        lines.append(
            f"| {s['id']} | {s['kind']} | {pct(s['best_similarity'])} "
            f"| {pct(s['keyword_coverage'])} |"
        )
    if sweep["follow_ups"]:
        lines += [
            "",
            "## Takip soruları",
            "",
            "| Önceki → yeni | Beklenen | Tek başına (benz./kaps.) | Kabul |",
            "|---|---|---|---|",
        ]
        for p in sweep["follow_ups"]:
            lines.append(
                f"| {p['previous']} → {p['question']} | {p['expect']} | "
                f"{pct(p['alone_similarity'])} / {pct(p['alone_coverage'])} | "
                f"{'evet' if p['admitted'] else 'hayır'} |"
            )
        if sweep["follow_up_grid"]:
            lines += ["", "| Takip tabanı | Doğru karar |", "|---|---|"]
        lines += [
            f"| {r['floor']} | {r['correct']}/{r['total']} |" for r in sweep["follow_up_grid"]
        ]
    if sweep["gaps"]:
        lines += ["", "## Boşluklar", ""] + [f"- {gap}" for gap in sweep["gaps"]]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.retrieval_sweep", description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--split", choices=[s.value for s in Split] + ["all"], required=True)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    parser.add_argument("--files-root", type=Path, default=Path(".."))
    parser.add_argument("--repo", type=Path, default=Path(".."))
    parser.add_argument("--database-url")
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--follow-ups", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    sweep = run_sweep(args)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{sweep['sweep_id']}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(sweep, file, ensure_ascii=False, indent=2)
    with path.with_suffix(".md").open("x", encoding="utf-8") as file:
        file.write(render_markdown(sweep))
    print(f"Karşılaştırma: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
