"""Q&A baseline koşusu: gold set'i gerçek soru-cevap hattından geçirir, konfigürasyonu kaydeder.

Kullanım (evaluation/ içinden, backend kurulu ve veritabanı açıkken):

    python -m harness.run --gold gold_sets/BLM2512/gold_set.json --split heldout \
        --condition full --files-root .. --out runs/

Her soru kendi veritabanı işleminde sorulur ve geri alınır: koşu sohbet/mesaj kaydı bırakmaz,
eğitmen analitiğini kirletmez. Çıktı `runs/<run_id>.json` (tam kayıt) ve `.md` (özet).
"""

import argparse
import math
import statistics
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from harness.conditions import Condition
from harness.fingerprint import file_sha256, text_sha256
from harness.metrics import accuracy, hallucination, retrieval, scope
from harness.schemas import (
    CorpusSnapshot,
    GoldItem,
    ItemKind,
    ItemResult,
    MetricValue,
    RunConfig,
    RunRecord,
    SourceLocator,
    Split,
    load_gold_set,
    load_manifest,
)
from harness.validate import (
    MIN_OUT_OF_SCOPE,
    MIN_REVIEWED_ANSWERABLE,
    item_gaps,
    structural_errors,
)

RECALL_K = 5

SUPPORTED_CONDITIONS = {Condition.FULL}


@dataclass
class Answer:
    """Soru-cevap hattının değerlendirme için gereken kısmı (AskResponse'tan bağımsız)."""

    outcome: str
    declined: bool
    mode: str
    model: str | None
    text: str | None
    cited_source_ids: list[str]
    retrieved_source_ids: list[str]
    best_similarity: float | None


AskFn = Callable[[str], Answer]
LocateFn = Callable[[str], SourceLocator | None]


def select_items(
    items: Sequence[GoldItem], split: Split | None, include_unreviewed: bool
) -> tuple[list[GoldItem], list[str]]:
    """Koşulacak sorular. Kalibrasyon ve held-out asla karışmaz; `split=None` yalnızca açıkça."""
    gaps: list[str] = []
    selected = [item for item in items if split is None or item.split is split]
    if not include_unreviewed:
        unreviewed = [item.id for item in selected if not item.reviewed]
        if unreviewed:
            gaps.append(
                f"{len(unreviewed)} soru eğitmen incelemesi olmadığı için koşulmadı: "
                + ", ".join(unreviewed[:10])
                + (" …" if len(unreviewed) > 10 else "")
            )
        selected = [item for item in selected if item.reviewed]
    return selected, gaps


def evaluate(
    items: Sequence[GoldItem],
    ask: AskFn,
    locate: LocateFn,
    clock: Callable[[], float] = time.perf_counter,
) -> list[ItemResult]:
    results: list[ItemResult] = []
    for item in items:
        started = clock()
        try:
            answer = ask(item.question)
        except Exception as exc:  # noqa: BLE001 — hata kaydedilir, koşu sürer
            results.append(
                ItemResult(
                    id=item.id,
                    split=item.split,
                    kind=item.kind,
                    outcome=None,
                    declined=None,
                    mode=None,
                    model=None,
                    answer=None,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        elapsed_ms = (clock() - started) * 1000
        results.append(
            ItemResult(
                id=item.id,
                split=item.split,
                kind=item.kind,
                outcome=answer.outcome,
                declined=answer.declined,
                mode=answer.mode,
                model=answer.model,
                answer=answer.text,
                cited=_locate_all(answer.cited_source_ids, locate),
                retrieved=_locate_all(answer.retrieved_source_ids, locate),
                best_similarity=answer.best_similarity,
                latency_ms=round(elapsed_ms, 1),
            )
        )
    return results


def _locate_all(source_ids: Sequence[str], locate: LocateFn) -> list[SourceLocator]:
    return [loc for loc in (locate(source_id) for source_id in source_ids) if loc is not None]


def compute_metrics(
    items: Sequence[GoldItem], results: Sequence[ItemResult]
) -> tuple[dict[str, MetricValue], list[str]]:
    """Judge gerektirmeyen metrikler; gerektirenler değer yerine açık boşlukla döner."""
    by_id = {item.id: item for item in items}
    ok = [r for r in results if r.error is None]
    metrics: dict[str, MetricValue] = {}
    gaps: list[str] = []

    errors = len(results) - len(ok)
    if errors:
        gaps.append(f"{errors} soru hata verdi; metriklerin paydalarına girmedi")

    answerable = [r for r in ok if r.kind is ItemKind.ANSWERABLE]
    out_of_scope = [r for r in ok if r.kind is ItemKind.OUT_OF_SCOPE]

    with_evidence = [r for r in answerable if by_id[r.id].evidence]
    metrics[f"retrieval_recall_at_{RECALL_K}"] = _metric(
        lambda: retrieval.recall_at_k(
            [r.retrieved for r in with_evidence],
            [by_id[r.id].evidence for r in with_evidence],
            k=RECALL_K,
            match=SourceLocator.matches,
        ),
        denominator=len(with_evidence),
        target=f">= {retrieval.TARGET}",
        empty_gap="gold kanıtı işaretlenmiş cevaplanabilir soru yok",
    )
    declined_oos = [bool(r.declined) for r in out_of_scope]
    metrics["out_of_scope_decline_rate"] = _metric(
        lambda: scope.decline_rate(declined_oos),
        denominator=len(declined_oos),
        numerator=sum(declined_oos),
        target=f">= {scope.TARGET_DECLINE}",
        empty_gap="kapsam dışı soru yok",
    )
    declined_ans = [bool(r.declined) for r in answerable]
    metrics["answerable_over_refusal_rate"] = _metric(
        lambda: scope.over_refusal_rate(declined_ans),
        denominator=len(declined_ans),
        numerator=sum(declined_ans),
        target=f"<= {scope.TARGET_OVER_REFUSAL_MAX}",
        empty_gap="cevaplanabilir soru yok",
    )
    answered = [r for r in answerable if not r.declined]
    cited = [bool(r.cited) for r in answered]
    metrics["citation_presence_rate"] = _metric(
        lambda: sum(cited) / len(cited),
        denominator=len(cited),
        numerator=sum(cited),
        empty_gap="cevaplanmış soru yok",
    )
    failures = [r.outcome == "provider_failure" for r in ok]
    metrics["provider_failure_rate"] = _metric(
        lambda: sum(failures) / len(failures),
        denominator=len(failures),
        numerator=sum(failures),
        empty_gap="koşulan soru yok",
    )
    latencies = sorted(r.latency_ms for r in ok if r.latency_ms is not None)
    metrics["latency_p50_ms"] = _metric(
        lambda: statistics.median(latencies),
        denominator=len(latencies),
        empty_gap="süre ölçülmedi",
    )
    metrics["latency_p95_ms"] = _metric(
        lambda: _percentile(latencies, 0.95),
        denominator=len(latencies),
        empty_gap="süre ölçülmedi",
    )

    judge_gap = "judge kalibre edilmedi; değer üretilmedi (#13)"
    metrics["answer_fully_correct_rate"] = MetricValue(
        value=None, denominator=len(answerable), target=f">= {accuracy.TARGET}", gap=judge_gap
    )
    metrics["answers_with_unsupported_claim_rate"] = MetricValue(
        value=None,
        denominator=len(answered),
        target=f"<= {hallucination.TARGET_MAX}",
        gap=judge_gap,
    )
    gaps.append(
        "Maliyet (token/ücret) kaydedilmiyor: soru-cevap hattı kullanım bilgisi döndürmüyor"
    )

    reviewed_answerable = sum(1 for i in items if i.kind is ItemKind.ANSWERABLE and i.reviewed)
    if reviewed_answerable < MIN_REVIEWED_ANSWERABLE:
        gaps.append(
            f"Eğitmen incelemeli cevaplanabilir soru {reviewed_answerable}/"
            f"{MIN_REVIEWED_ANSWERABLE}: baseline kabul için yetersiz"
        )
    oos_count = sum(1 for i in items if i.kind is ItemKind.OUT_OF_SCOPE)
    if oos_count < MIN_OUT_OF_SCOPE:
        gaps.append(f"Kapsam dışı soru {oos_count}/{MIN_OUT_OF_SCOPE}")
    return metrics, gaps


def _metric(
    compute: Callable[[], float],
    denominator: int,
    numerator: int | None = None,
    target: str | None = None,
    empty_gap: str = "payda sıfır",
) -> MetricValue:
    if denominator == 0:
        return MetricValue(value=None, denominator=0, target=target, gap=empty_gap)
    return MetricValue(
        value=round(compute(), 4), numerator=numerator, denominator=denominator, target=target
    )


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    """En yakın sıra yöntemi; küçük örneklerde abartılı ara değer üretmez."""
    index = max(0, min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1))
    return sorted_values[index]


def git_state(repo: Path) -> tuple[str | None, bool | None]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return commit, bool(status.strip())


def run_id_for(started: datetime, condition: Condition, split: Split | None, commit: str | None):
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    split_name = split.value if split else "all"
    # Aynı saniyede başlayan iki koşu birbirinin üzerine yazmasın.
    return (
        f"{stamp}_{condition.value}_{split_name}_{(commit or 'nogit')[:8]}_{uuid.uuid4().hex[:6]}"
    )


# --- Gerçek hat (veritabanı + backend) ---------------------------------------------------------


def _backend_ask(engine, course_id: int, llm) -> AskFn:
    """Her soru ayrı işlemde: hat commit etse bile en sonda geri alınır."""
    from sqlalchemy.orm import Session

    from app.db.models import Course
    from app.qa import service
    from app.schemas.ask import AskRequest

    def ask(question: str) -> Answer:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    course = db.get(Course, course_id)
                    response = service.ask(
                        db, course, AskRequest(course_id=course_id, question=question), llm
                    )
            finally:
                transaction.rollback()
        return Answer(
            outcome=response.outcome,
            declined=response.declined,
            mode=response.mode,
            model=response.model,
            text=response.answer,
            cited_source_ids=[c.source_id for c in response.citations],
            retrieved_source_ids=[hit.source_id for hit in response.retrieval],
            best_similarity=response.best_similarity,
        )

    return ask


def _run_config(
    condition: Condition,
    split: Split | None,
    gold_path: Path,
    manifest_path: Path,
    repo: Path,
) -> RunConfig:
    from app.core.config import settings
    from app.generation.answer import SYSTEM_PROMPT
    from app.retrieval import fusion, hybrid

    commit, dirty = git_state(repo)
    return RunConfig(
        condition=condition.value,
        split=split,
        git_commit=commit,
        git_dirty=dirty,
        gold_set_sha256=file_sha256(gold_path),
        manifest_sha256=file_sha256(manifest_path),
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model if settings.llm_api_key else None,
        llm_base_url=_sanitized_url(settings.llm_base_url),
        llm_enabled=bool(settings.llm_api_key),
        prompt_sha256=text_sha256(SYSTEM_PROMPT),
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        retrieval={
            "k": RECALL_K,
            "min_similarity": settings.retrieval_min_similarity,
            "candidates_per_method": hybrid.CANDIDATES_PER_METHOD,
            "context_weight": hybrid.CONTEXT_WEIGHT,
            "rrf_k": fusion.RRF_K,
            "min_keyword_coverage": settings.retrieval_min_keyword_coverage,
            "follow_up_min_similarity": settings.retrieval_follow_up_min_similarity,
        },
    )


def _sanitized_url(url: str) -> str:
    """Şema, sunucu, port ve yol; kullanıcı bilgisi ve sorgu (olası anahtar) atılır."""
    parts = urlparse(url)
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}{parts.path}"


def run_baseline(args: argparse.Namespace) -> RunRecord:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.embeddings.provider import get_embedder
    from app.llm.gateway import select_client
    from app.retrieval.index import inventory
    from harness.corpus import CorpusError, Locator, find_course, snapshot

    condition = Condition(args.condition)
    if condition not in SUPPORTED_CONDITIONS:
        raise SystemExit(f"'{condition.value}' koşulu henüz uygulanmadı; şimdilik: full")
    split = None if args.split == "all" else Split(args.split)

    gold = load_gold_set(args.gold)
    manifest_path = args.manifest or args.gold.parent / gold.manifest
    manifest = load_manifest(manifest_path)
    errors = structural_errors(gold, manifest)
    if errors:
        details = "\n  ".join(errors)
        raise SystemExit(f"Gold set tutarsız, koşu yapılmadı:\n  {details}")
    items, selection_gaps = select_items(gold.items, split, args.include_unreviewed)

    started = datetime.now(UTC)
    config = _run_config(condition, split, args.gold, manifest_path, args.repo)
    engine = create_engine(args.database_url or settings.database_url)
    with Session(engine) as db:
        course = find_course(db, gold.course_code)
        locator = Locator(db, args.files_root)
        corpus = snapshot(db, course, manifest, locator)
        if corpus.unapproved_indexed and not args.allow_unapproved:
            raise CorpusError(
                "Envanterde onaylı olmayan doküman indekste: "
                + ", ".join(corpus.unapproved_indexed)
                + " (envantere ekleyin ya da dersten silin)"
            )
        identity = get_embedder().identity
        index = inventory(db, course.id)
        config = config.model_copy(
            update={"embedding_identity": identity, "index_fingerprint": index.fingerprint}
        )
        results = evaluate(items, _backend_ask(engine, course.id, select_client()), locator.locate)
    metrics, metric_gaps = compute_metrics(items, results)

    gaps = selection_gaps + item_gaps(gold) + metric_gaps + _corpus_gaps(corpus)
    gaps += [f"Eksik girdi: {m.what} (sorumlu: {m.owner})" for m in manifest.missing_inputs]
    if index.stale(identity):
        gaps.append(
            f"{index.stale(identity)} parça etkin embedder'la ({identity}) vektörleştirilmemiş; "
            "anlamsal arama bunları görmedi (python -m app.scripts.reembed)"
        )
    if config.git_dirty:
        gaps.append("Çalışma ağacında commit'lenmemiş değişiklik var; koşu tam tekrarlanamaz")
    if not config.llm_enabled:
        gaps.append("LLM anahtarı yok: cevaplar LLM'siz alıntı modunda üretildi")
    return RunRecord(
        run_id=run_id_for(started, condition, split, config.git_commit),
        started_at=started,
        finished_at=datetime.now(UTC),
        config=config,
        corpus=corpus,
        items=results,
        metrics=metrics,
        gaps=gaps,
    )


def _corpus_gaps(corpus: CorpusSnapshot) -> list[str]:
    gaps = []
    if corpus.approved_not_indexed:
        gaps.append(
            f"Envanterde onaylı ama indekste olmayan {len(corpus.approved_not_indexed)} doküman"
        )
    if corpus.unapproved_indexed:
        gaps.append("Onaysız doküman indekste (--allow-unapproved ile koşuldu)")
    return gaps


def write_outputs(record: RunRecord, out_dir: Path) -> Path:
    from harness.report import render_markdown

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{record.run_id}.json"
    # "x": var olan bir koşu kaydının üzerine asla yazılmaz.
    with path.open("x", encoding="utf-8") as file:
        file.write(record.model_dump_json(indent=2))
    with path.with_suffix(".md").open("x", encoding="utf-8") as file:
        file.write(render_markdown(record))
    return path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.run", description=__doc__)
    parser.add_argument("--gold", type=Path, required=True, help="gold_set.json")
    parser.add_argument("--manifest", type=Path, help="Varsayılan: gold set'teki manifest adı")
    parser.add_argument(
        "--split",
        choices=[s.value for s in Split] + ["all"],
        required=True,
        help="Kalibrasyon ve held-out ayrı koşulur; 'all' yalnızca keşif içindir",
    )
    parser.add_argument("--condition", default=Condition.FULL.value)
    parser.add_argument("--out", type=Path, default=Path("runs"))
    parser.add_argument(
        "--files-root",
        type=Path,
        default=Path(".."),
        help="Göreli dosya yollarının kökü (docker-compose'da repo kökü)",
    )
    parser.add_argument("--repo", type=Path, default=Path(".."), help="git bilgisi için repo kökü")
    parser.add_argument("--database-url", help="Varsayılan: DATABASE_URL")
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--allow-unapproved", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    # Windows konsolu (cp1254) Türkçe karakterleri bozmasın.
    sys.stdout.reconfigure(encoding="utf-8")
    record = run_baseline(args)
    path = write_outputs(record, args.out)
    print(f"Koşu kaydı: {path}")
    for gap in record.gaps:
        print(f"  boşluk: {gap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
