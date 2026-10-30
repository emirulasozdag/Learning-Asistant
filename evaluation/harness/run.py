"""Q&A koşusu: gold set'i dört koşuldan (no_rag, basic_rag, full, full_video_time) geçirir.

Kullanım (evaluation/ içinden, backend kurulu ve veritabanı açıkken):

    python -m harness.run --gold gold_sets/BLM2512/gold_set.json --split heldout \
        --condition all --files-root .. --out runs/

Birden fazla koşul aynı sorular, aynı üretici model ve aynı indeksle (tek parmak izi) koşulur;
koşu kayıtları ortak `batch_id` taşır ve `runs/<batch_id>.compare.md` karşılaştırma tablosu yazılır.
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
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from harness import conditions
from harness.conditions import Condition
from harness.fingerprint import file_sha256, text_sha256
from harness.metrics import accuracy, citation, hallucination, retrieval, scope
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
    # Getirilen parçaların metni, `retrieved_source_ids` ile aynı sırada.
    retrieved_texts: list[str | None] = field(default_factory=list)


AskFn = Callable[[GoldItem], Answer]
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
            answer = ask(item)
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
        retrieved, retrieved_text = _locate_with_text(
            answer.retrieved_source_ids, answer.retrieved_texts, locate
        )
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
                retrieved=retrieved,
                retrieved_text=retrieved_text,
                best_similarity=answer.best_similarity,
                latency_ms=round(elapsed_ms, 1),
            )
        )
    return results


def _locate_all(source_ids: Sequence[str], locate: LocateFn) -> list[SourceLocator]:
    return [loc for loc in (locate(source_id) for source_id in source_ids) if loc is not None]


def _locate_with_text(
    source_ids: Sequence[str], texts: Sequence[str | None], locate: LocateFn
) -> tuple[list[SourceLocator], list[str]]:
    """Konumu bulunan parçalar ve metinleri.

    Bir parçanın bile metni eksikse metin listesi boş kalır: judge eksik kanıta göre etiketlemez,
    boşluk yazar.
    """
    located = [(locate(source_id), index) for index, source_id in enumerate(source_ids)]
    pairs = [(loc, index) for loc, index in located if loc is not None]
    found = [texts[index] if index < len(texts) else None for _, index in pairs]
    if not all(found):
        return [loc for loc, _ in pairs], []
    return [loc for loc, _ in pairs], [text for text in found if text]


def compute_metrics(
    items: Sequence[GoldItem],
    results: Sequence[ItemResult],
    condition: Condition = Condition.FULL,
) -> tuple[dict[str, MetricValue], list[str]]:
    """Judge gerektirmeyen metrikler; gerektirenler değer yerine açık boşlukla döner.

    no_rag'de arama ve alıntı yoktur: bu metrikler 0 değil, "koşulda yok" boşluğu olarak yazılır.
    """
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
    cited_with_evidence = [r for r in answered if by_id[r.id].evidence]
    metrics["citation_evidence_coverage"] = _metric(
        lambda: citation.evidence_coverage(
            [r.cited for r in cited_with_evidence],
            [by_id[r.id].evidence for r in cited_with_evidence],
            match=SourceLocator.matches,
        ),
        denominator=len(cited_with_evidence),
        empty_gap="gold kanıtı olan cevaplanmış soru yok",
    )
    hits, total_citations = citation.precision_counts(
        [r.cited for r in cited_with_evidence],
        [by_id[r.id].evidence for r in cited_with_evidence],
        match=SourceLocator.matches,
    )
    metrics["citation_precision"] = _metric(
        lambda: hits / total_citations,
        denominator=total_citations,
        numerator=hits,
        empty_gap="gold kanıtı olan cevaplarda alıntı yok",
    )
    failures = [r.outcome == "provider_failure" for r in ok]
    metrics["provider_failure_rate"] = _metric(
        lambda: sum(failures) / len(failures),
        denominator=len(failures),
        numerator=sum(failures),
        empty_gap="koşulan soru yok",
    )
    # #10: cevap üretildi ama iddia kontrolü yapılamadı (judge yok / hata); alıntı gösterildi.
    unchecked = [r.outcome == "verification_failure" for r in ok]
    metrics["verification_failure_rate"] = _metric(
        lambda: sum(unchecked) / len(unchecked),
        denominator=len(unchecked),
        numerator=sum(unchecked),
        empty_gap="koşulan soru yok",
    )
    if condition is Condition.NO_RAG:
        for name in (
            f"retrieval_recall_at_{RECALL_K}",
            "citation_presence_rate",
            "citation_evidence_coverage",
            "citation_precision",
        ):
            metrics[name] = MetricValue(
                value=None,
                denominator=0,
                target=metrics[name].target,
                gap="no_rag koşulunda arama/alıntı yok",
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

    # Judge/insan etiketi gerektirir: `python -m harness.trust` koşu kaydıyla hesaplar.
    judge_gap = "insan/judge etiketi gerekli; harness.trust ile hesaplanır"
    metrics["answer_fully_correct_rate"] = MetricValue(
        value=None, denominator=len(answerable), target=f">= {accuracy.TARGET}", gap=judge_gap
    )
    metrics["answers_with_unsupported_claim_rate"] = MetricValue(
        value=None,
        denominator=len(answered),
        target=f"<= {hallucination.TARGET_MAX}",
        gap=judge_gap,
    )
    metrics["unsupported_claim_rate"] = MetricValue(value=None, denominator=0, gap=judge_gap)
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


def _backend_ask(
    engine,
    course_id: int,
    llm,
    condition: Condition = Condition.FULL,
    playback_documents: dict[str, int] | None = None,
) -> AskFn:
    """Her soru ayrı işlemde: hat commit etse bile en sonda geri alınır.

    `playback_documents`: video dokümanının SHA-256'sı → doküman kimliği (full_video_time).
    """
    from sqlalchemy.orm import Session

    from app.db.models import Chunk, Course
    from app.qa import service
    from app.schemas.ask import AskRequest, VideoRef

    def _chunk_text(db: Session, source_id: str) -> str | None:
        chunk = db.get(Chunk, int(source_id)) if source_id.isdigit() else None
        return chunk.text if chunk is not None else None

    def _video(item: GoldItem) -> VideoRef | None:
        if condition is not Condition.FULL_VIDEO_TIME or item.playback is None:
            return None
        document_id = (playback_documents or {}).get(item.playback.document_sha256)
        if document_id is None:
            raise LookupError(f"{item.id}: oynatma konumundaki video indekste yok")
        return VideoRef(document_id=document_id, time_s=item.playback.time_s)

    def ask(item: GoldItem) -> Answer:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                    course = db.get(Course, course_id)
                    if condition in (Condition.NO_RAG, Condition.BASIC_RAG):
                        return _baseline_answer(db, course, item.question, llm, condition)
                    request = AskRequest(
                        course_id=course_id, question=item.question, video=_video(item)
                    )
                    response = service.ask(db, course, request, llm)
                    # Judge ve değerlendirici iddiaları modelin gördüğü pasajlara göre etiketler.
                    texts = [_chunk_text(db, hit.source_id) for hit in response.retrieval]
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
            retrieved_texts=texts,
        )

    return ask


def _baseline_answer(db, course, question: str, llm, condition: Condition) -> Answer:
    """no_rag / basic_rag: minimal karşılaştırma hatları (`harness.conditions`)."""
    passages: list[conditions.Passage] = []
    best_similarity = None
    if condition is Condition.BASIC_RAG:
        from app.embeddings.provider import get_embedder
        from app.retrieval.dense import dense_search

        embedder = get_embedder()
        hits = dense_search(
            db, course, embedder.embed_query(question), conditions.BASIC_K, embedder.identity
        )
        passages = [conditions.Passage(hit.source_id, hit.text) for hit in hits]
        best_similarity = max((h.dense_score for h in hits if h.dense_score), default=None)
        result = conditions.basic_rag(question, course.name, passages, llm)
    else:
        result = conditions.closed_book(question, course.name, llm)
    return Answer(
        outcome=result.outcome,
        declined=result.outcome == "model_refusal",
        mode="llm",
        model=result.model,
        text=result.text,
        cited_source_ids=result.cited_source_ids,
        retrieved_source_ids=[p.source_id for p in result.retrieved],
        best_similarity=best_similarity,
        retrieved_texts=[p.text for p in result.retrieved],
    )


def playback_documents(db, course, locator) -> dict[str, int]:
    """Dersin video/ses dokümanları: SHA-256 → doküman kimliği."""
    from sqlalchemy import select

    from app.db.models import Document

    documents = db.scalars(select(Document).where(Document.course_id == course.id))
    result = {}
    for document in documents:
        sha = locator.document_sha256(document)
        if sha is not None:
            result[sha] = document.id
    return result


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
    prompt = {
        Condition.NO_RAG: conditions.CLOSED_BOOK_PROMPT,
        Condition.BASIC_RAG: conditions.BASIC_RAG_PROMPT,
    }.get(condition, SYSTEM_PROMPT)
    return RunConfig(
        condition=condition.value,
        condition_settings=conditions.SETTINGS[condition],
        split=split,
        git_commit=commit,
        git_dirty=dirty,
        gold_set_sha256=file_sha256(gold_path),
        manifest_sha256=file_sha256(manifest_path),
        llm_provider=settings.llm_provider,
        llm_model=settings.generator_model if settings.llm_api_key else None,
        llm_base_url=_sanitized_url(settings.llm_endpoint),
        llm_enabled=bool(settings.llm_api_key),
        prompt_sha256=text_sha256(prompt),
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


def parse_conditions(values: Sequence[str]) -> list[Condition]:
    """`all` ya da koşul adları; sıra korunur, tekrar atılır."""
    if "all" in values:
        return list(Condition)
    result: list[Condition] = []
    for value in values:
        condition = Condition(value)
        if condition not in result:
            result.append(condition)
    return result


def run_conditions(args: argparse.Namespace) -> list[RunRecord]:
    """Seçilen koşulları aynı sorular, model ve indeksle koşar (tek envanter/indeks kontrolü)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.embeddings.provider import get_embedder
    from app.llm.gateway import select_client
    from app.retrieval.index import inventory
    from harness.corpus import CorpusError, Locator, find_course, snapshot

    selected = parse_conditions(args.condition)
    split = None if args.split == "all" else Split(args.split)

    gold = load_gold_set(args.gold)
    manifest_path = args.manifest or args.gold.parent / gold.manifest
    manifest = load_manifest(manifest_path)
    errors = structural_errors(gold, manifest)
    if errors:
        details = "\n  ".join(errors)
        raise SystemExit(f"Gold set tutarsız, koşu yapılmadı:\n  {details}")
    items, selection_gaps = select_items(gold.items, split, args.include_unreviewed)

    llm = select_client()
    baselines = [c for c in selected if c in (Condition.NO_RAG, Condition.BASIC_RAG)]
    if baselines and llm is None:
        names = ", ".join(c.value for c in baselines)
        raise SystemExit(f"{names} koşulları LLM olmadan koşulamaz (LLM_API_KEY)")

    batch_started = datetime.now(UTC)
    engine = create_engine(args.database_url or settings.database_url)
    records: list[RunRecord] = []
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
        videos = playback_documents(db, course, locator)
        commit, _ = git_state(args.repo)
        batch_id = run_id_for(batch_started, Condition.FULL, split, commit).replace(
            "_full_", "_batch_"
        )
        for condition in selected:
            started = datetime.now(UTC)
            config = _run_config(condition, split, args.gold, manifest_path, args.repo)
            config = config.model_copy(
                update={
                    "embedding_identity": identity,
                    "index_fingerprint": index.fingerprint,
                    "batch_id": batch_id if len(selected) > 1 else None,
                }
            )
            ask = _backend_ask(engine, course.id, llm, condition, videos)
            results = evaluate(items, ask, locator.locate)
            metrics, metric_gaps = compute_metrics(items, results, condition)
            gaps = selection_gaps + item_gaps(gold) + metric_gaps + _corpus_gaps(corpus)
            gaps += condition_gaps(condition, items)
            gaps += [f"Eksik girdi: {m.what} (sorumlu: {m.owner})" for m in manifest.missing_inputs]
            if index.stale(identity):
                gaps.append(
                    f"{index.stale(identity)} parça etkin embedder'la ({identity}) "
                    "vektörleştirilmemiş; anlamsal arama bunları görmedi "
                    "(python -m app.scripts.reembed)"
                )
            if config.git_dirty:
                gaps.append(
                    "Çalışma ağacında commit'lenmemiş değişiklik var; koşu tam tekrarlanamaz"
                )
            if not config.llm_enabled:
                gaps.append("LLM anahtarı yok: cevaplar LLM'siz alıntı modunda üretildi")
            records.append(
                RunRecord(
                    run_id=run_id_for(started, condition, split, config.git_commit),
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    config=config,
                    corpus=corpus,
                    items=results,
                    metrics=metrics,
                    gaps=gaps,
                )
            )
    return records


def condition_gaps(condition: Condition, items: Sequence[GoldItem]) -> list[str]:
    """Koşula özgü eksikler (ör. oynatma konumu olmayan sorular)."""
    if condition is not Condition.FULL_VIDEO_TIME:
        return []
    with_playback = sum(1 for item in items if item.playback is not None)
    if with_playback == 0:
        return [
            "Hiçbir soruda oynatma konumu (playback) yok: full_video_time, full ile aynı koşuldu"
        ]
    if with_playback < len(items):
        return [
            f"{len(items) - with_playback}/{len(items)} soruda oynatma konumu yok; "
            "bu sorular full ile aynı koşuldu"
        ]
    return []


def _corpus_gaps(corpus: CorpusSnapshot) -> list[str]:
    gaps = []
    if corpus.approved_not_indexed:
        gaps.append(
            f"Envanterde onaylı ama indekste olmayan {len(corpus.approved_not_indexed)} doküman"
        )
    if corpus.unapproved_indexed:
        gaps.append("Onaysız doküman indekste (--allow-unapproved ile koşuldu)")
    return gaps


def write_comparison(records: Sequence[RunRecord], out_dir: Path) -> Path | None:
    """Aynı batch'teki koşulların karşılaştırma tablosu; tek koşulda yazılmaz."""
    from harness.report import render_comparison

    batch_id = records[0].config.batch_id if records else None
    if batch_id is None:
        return None
    path = out_dir / f"{batch_id}.compare.md"
    with path.open("x", encoding="utf-8") as file:
        file.write(render_comparison(records))
    return path


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
    parser.add_argument(
        "--condition",
        nargs="+",
        default=[Condition.FULL.value],
        choices=[c.value for c in Condition] + ["all"],
        help="Bir ya da birden fazla koşul; 'all' dördünü aynı ayarlarla koşar",
    )
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
    records = run_conditions(args)
    for record in records:
        path = write_outputs(record, args.out)
        print(f"Koşu kaydı ({record.config.condition}): {path}")
        for gap in record.gaps:
            print(f"  boşluk: {gap}")
    comparison = write_comparison(records, args.out)
    if comparison:
        print(f"Karşılaştırma: {comparison}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
