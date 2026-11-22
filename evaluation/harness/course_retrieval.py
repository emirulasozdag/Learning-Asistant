"""Çok dersli arama kalitesi, ders filtresi, sorgu planları ve parmak izleri (#29). LLM yok.

Kullanım (evaluation/ içinden, backend kurulu ve veritabanı açıkken):

    python -m harness.course_retrieval \
        --gold gold_sets/6.006/gold_set.json gold_sets/18.06/gold_set.json \
        --split all --files-root .. --out runs/ [--include-unreviewed]

Her ders için:
- Envanter kontrolü (onaysız doküman indeksteyse ölçüm yapılmaz) ve parmak izleri: derlem,
  embedder kimliği, metin indeksi, kare indeksi (OCR metni, çıkarıcı, yorumlayıcı).
- Dallar: `hybrid` (üretim), `dense`, `lexical`, `hybrid_playback` (oynatma konumlu sorular),
  `frames` (kare araması). Her dalda ders filtreli Recall@5, ilk doğru sonucun sırası ve soru
  türüne göre (`concept`, `lexical`, `code`, `diagram`, `formula`) kırılım.
- Ders filtresi: her dalın her sonucu dersin dokümanı mı; ayrıca her soru diğer derslerde de
  sorulur ve sonuçların o derste kaldığı denetlenir (sızıntı sayısı 0 olmalı).
- Kusur dedektörleri: kısa sonuç listesi (aday kıtlığı), ilk 5'te tekrar (aynı metin ya da aynı
  konum), kapıdan geçemeyen cevaplanabilir soru, kare–transkript hizası.
- Sorgu planları: her dalın veritabanına gönderdiği SELECT'ler yakalanır ve
  `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` ile yeniden çalıştırılır. Ders filtresinden sonra
  kesin arama beklenir; HNSW indeksine kayan plan (aday kaybı riski) işaretlenir.

Ekip taslağı sorular (`team_draft`) yalnızca `--include-unreviewed` ile koşulur ve rapor bunu
"taslak set" olarak yazar. Çıktı `<out>/<id>.json` ve `.md`; var olan dosyanın üzerine yazılmaz.
"""

import argparse
import hashlib
import json
import sys
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from harness.metrics import retrieval as retrieval_metrics
from harness.retrieval_sweep import first_hit_rank
from harness.run import RECALL_K, git_state, select_items
from harness.schemas import (
    GoldItem,
    ItemKind,
    QueryType,
    SourceLocator,
    Split,
    load_gold_set,
    load_manifest,
)
from harness.validate import structural_errors

HYBRID = "hybrid"
DENSE = "dense"
LEXICAL = "lexical"
PLAYBACK = "hybrid_playback"
FRAMES = "frames"
BRANCHES = (HYBRID, DENSE, LEXICAL, PLAYBACK, FRAMES)
# İlk doğru sonucun sırası bu derinliğe kadar aranır.
RANK_DEPTH = 50
# Bu sayının altındaki soru grubu "küçük örnek" olarak işaretlenir.
MIN_ITEMS = 10
# İki zaman aralığı, kısa olanın bu oranı ortaksa aynı yer sayılır (tekrar).
OVERLAP_DUPLICATE = 0.5
# Kare süresi bu kadar saniye videonun süresini aşarsa hiza hatası sayılır.
DURATION_TOLERANCE_S = 1.0


@dataclass(frozen=True)
class Hit:
    """Bir dalın döndürdüğü sonuç: kaynak konumu ve ders filtresi denetimi için doküman."""

    source_id: str
    document_id: int
    locator: SourceLocator | None
    text_sha256: str


@dataclass
class BranchResult:
    branch: str
    items: int
    recall_at_5: float | None
    recall_by_type: dict[str, float | None]
    items_by_type: dict[str, int]
    first_hit_rank: dict[str, int | None] = field(default_factory=dict)
    # Aday kıtlığı: ilk 5'i dolduramayan soru (derste en az 5 aranabilir birim varken).
    short_lists: list[str] = field(default_factory=list)
    # İlk 5'te önceki bir sonucun tekrarı (aynı metin ya da aynı konum) olan soru → tekrar sayısı.
    duplicates: dict[str, int] = field(default_factory=dict)
    # Dersin dışından gelen sonuç (olmamalı).
    foreign_hits: int = 0


# --- Saf hesaplar (veritabanısız test edilir) ------------------------------------------------


def duplicate_count(hits: Sequence[Hit], k: int = RECALL_K) -> int:
    """İlk k sonuçta, kendinden önceki bir sonucun aynısı olanların sayısı.

    Aynı: metni birebir aynı ya da aynı dokümanda aynı sayfa / büyük ölçüde aynı zaman aralığı
    (kısa olanın en az `OVERLAP_DUPLICATE` kadarı ortak; ör. ardışık özdeş kareler). Video
    parçaları bilerek ~20 sn üst üste biner; bu kadarlık komşuluk tekrar sayılmaz.
    """
    seen: list[Hit] = []
    duplicates = 0
    for hit in hits[:k]:
        if any(_same(hit, other) for other in seen):
            duplicates += 1
        seen.append(hit)
    return duplicates


def _same(a: Hit, b: Hit) -> bool:
    if a.text_sha256 and a.text_sha256 == b.text_sha256:
        return True
    if a.locator is None or b.locator is None or a.document_id != b.document_id:
        return False
    if a.locator.page is not None:
        return a.locator.page == b.locator.page
    if a.locator.t_start is None or b.locator.t_start is None:
        return False
    assert a.locator.t_end is not None and b.locator.t_end is not None
    shared = min(a.locator.t_end, b.locator.t_end) - max(a.locator.t_start, b.locator.t_start)
    shorter = min(a.locator.t_end - a.locator.t_start, b.locator.t_end - b.locator.t_start)
    return shared > 0 and (shorter <= 0 or shared / shorter >= OVERLAP_DUPLICATE)


def summarize_branch(
    branch: str,
    items: Sequence[GoldItem],
    hits: dict[str, list[Hit]],
    course_documents: set[int],
    searchable_units: int,
) -> BranchResult:
    """Bir dalın soruları üzerinden Recall@5, türe göre kırılım ve kusur sayaçları."""
    asked = [item for item in items if item.id in hits]
    ranks: dict[str, int | None] = {}
    short: list[str] = []
    duplicates: dict[str, int] = {}
    foreign = 0
    for item in asked:
        item_hits = hits[item.id]
        ranks[item.id] = first_hit_rank([h.locator for h in item_hits], item.evidence)
        if len(item_hits) < RECALL_K <= searchable_units:
            short.append(item.id)
        if count := duplicate_count(item_hits):
            duplicates[item.id] = count
        foreign += sum(h.document_id not in course_documents for h in item_hits)
    by_type: dict[str, float | None] = {}
    counts: dict[str, int] = {}
    for query_type in QueryType:
        group = [item for item in asked if item.retrieval_type is query_type]
        counts[query_type.value] = len(group)
        by_type[query_type.value] = _recall(group, hits)
    return BranchResult(
        branch=branch,
        items=len(asked),
        recall_at_5=_recall(asked, hits),
        recall_by_type=by_type,
        items_by_type=counts,
        first_hit_rank=ranks,
        short_lists=short,
        duplicates=duplicates,
        foreign_hits=foreign,
    )


def _recall(items: Sequence[GoldItem], hits: dict[str, list[Hit]]) -> float | None:
    with_evidence = [item for item in items if item.evidence]
    if not with_evidence:
        return None

    def match(gold: SourceLocator, hit: SourceLocator | None) -> bool:
        return hit is not None and gold.matches(hit)

    value = retrieval_metrics.recall_at_k(
        [[h.locator for h in hits[item.id]] for item in with_evidence],
        [item.evidence for item in with_evidence],
        k=RECALL_K,
        match=match,
    )
    return round(value, 4)


@dataclass
class PlanSummary:
    """Bir sorgunun planı: kullanılan düğüm türleri, indeksler ve süre."""

    query: str
    node_types: list[str]
    indexes: list[str]
    execution_ms: float | None
    # Vektör indeksi (HNSW) kullanıldı mı: ders filtresi sonradan uygulanırsa aday kaybolur.
    uses_vector_index: bool
    rows: int | None


def summarize_plan(label: str, plan: dict) -> PlanSummary:
    """`EXPLAIN (FORMAT JSON)` çıktısının ilk öğesi → özet."""
    nodes: list[str] = []
    indexes: list[str] = []

    def walk(node: dict) -> None:
        nodes.append(node.get("Node Type", "?"))
        if name := node.get("Index Name"):
            indexes.append(name)
        for child in node.get("Plans", []):
            walk(child)

    root = plan.get("Plan", {})
    walk(root)
    return PlanSummary(
        query=label,
        node_types=sorted(set(nodes)),
        indexes=sorted(set(indexes)),
        execution_ms=plan.get("Execution Time"),
        uses_vector_index=any("hnsw" in name.lower() for name in indexes),
        rows=root.get("Actual Rows"),
    )


@dataclass
class FrameAlignment:
    """Kare–transkript hizası (#29): kare zamanları videoyla ve konuşmayla tutarlı mı."""

    frames: int
    searchable: int
    # t_end <= t_start ya da t_frame aralığın dışında.
    invalid_interval: int
    # Kare videonun süresini aşıyor.
    beyond_duration: int
    # Aynı videoda ardışık iki kare zamanda çakışıyor.
    overlapping_neighbors: int
    # Aranabilir karenin aralığında hiç transkript parçası yok (bağlamsız kare).
    without_transcript: int
    # Ardışık kareler arasındaki boşluk (sn) toplamı; büyükse kare atlanmış olabilir.
    gap_total_s: float


def frame_alignment(
    frames: Sequence[tuple[int, int, float, float, float, str]],
    durations: dict[int, float | None],
    transcript_ranges: dict[int, list[tuple[float, float]]],
) -> FrameAlignment:
    """`frames`: (doküman, sıra, t_start, t_end, t_frame, durum) satırları."""
    invalid = beyond = overlapping = without = searchable = 0
    gap_total = 0.0
    previous: dict[int, tuple[float, float]] = {}
    for document_id, _, t_start, t_end, t_frame, status in sorted(frames, key=lambda f: f[:2]):
        if t_end <= t_start or not t_start <= t_frame <= t_end:
            invalid += 1
        duration = durations.get(document_id)
        if duration is not None and t_end > duration + DURATION_TOLERANCE_S:
            beyond += 1
        if document_id in previous:
            _, prev_end = previous[document_id]
            if t_start < prev_end:
                overlapping += 1
            else:
                gap_total += t_start - prev_end
        previous[document_id] = (t_start, t_end)
        if status in ("readable", "partial"):
            searchable += 1
            ranges = transcript_ranges.get(document_id, [])
            if not any(start < t_end and end > t_start for start, end in ranges):
                without += 1
    return FrameAlignment(
        frames=len(frames),
        searchable=searchable,
        invalid_interval=invalid,
        beyond_duration=beyond,
        overlapping_neighbors=overlapping,
        without_transcript=without,
        gap_total_s=round(gap_total, 1),
    )


# --- Veritabanı ile ölçüm --------------------------------------------------------------------


@contextmanager
def captured_selects(engine) -> Iterator[list[tuple[str, object]]]:
    """Bu blokta motorun çalıştırdığı SELECT'ler (sorgu, parametreler)."""
    from sqlalchemy import event

    statements: list[tuple[str, object]] = []

    def record(conn, cursor, statement, parameters, context, executemany):  # noqa: ARG001
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            statements.append((statement, parameters))

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


def explain(db, statement: str, parameters: object) -> dict:
    """Sorguyu `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` ile çalıştırır (yalnızca SELECT)."""
    connection = db.connection()
    row = connection.exec_driver_sql(
        "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
    ).scalar_one()
    plan = row if isinstance(row, list) else json.loads(row)
    return plan[0]


def _text_hash(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest() if text else ""


class CourseProbe:
    """Bir dersin dallarını aynı oturumda çalıştırır; sonuçları `Hit`e çevirir."""

    def __init__(self, db, course, locator, embedder, videos: dict[str, int]) -> None:
        from app.retrieval.hybrid import DENSE as DENSE_METHOD
        from app.retrieval.hybrid import LEXICAL as LEXICAL_METHOD
        from app.retrieval.hybrid import RetrievalParams

        self.db = db
        self.course = course
        self.locator = locator
        self.embedder = embedder
        self.videos = videos
        self.params = {
            HYBRID: RetrievalParams(),
            DENSE: RetrievalParams(methods=(DENSE_METHOD,)),
            LEXICAL: RetrievalParams(methods=(LEXICAL_METHOD,)),
        }

    def search(self, branch: str, question: str, playback=None, k: int = RANK_DEPTH):
        """Dalın arama çağrısı (konum çözmeden); oynatılan video derste yoksa None."""
        from app.retrieval.frames import frame_search
        from app.retrieval.hybrid import retrieve
        from app.retrieval.types import VideoPosition

        if branch == FRAMES:
            return frame_search(self.db, self.course, question, self.embedder, k=k)
        video = None
        if playback is not None:
            document_id = self.videos.get(playback.document_sha256)
            if document_id is None:
                return None
            video = VideoPosition(document_id, playback.time_s)
        return retrieve(
            self.db,
            self.course,
            question,
            video,
            k=k,
            embedder=self.embedder,
            params=self.params[HYBRID if branch == PLAYBACK else branch],
        )

    def search_with(self, params, question: str, playback=None, k: int = RECALL_K):
        """Verilen ayarlarla hibrit arama (değişke karşılaştırması); video derste yoksa None."""
        from app.retrieval.hybrid import retrieve
        from app.retrieval.types import VideoPosition

        video = None
        if playback is not None:
            document_id = self.videos.get(playback.document_sha256)
            if document_id is None:
                return None
            video = VideoPosition(document_id, playback.time_s)
        return retrieve(
            self.db, self.course, question, video, k=k, embedder=self.embedder, params=params
        )

    def hits(self, result) -> list[Hit]:
        return [
            Hit(p.source_id, p.document_id, self.locator.locate(p.source_id), _text_hash(p.text))
            for p in result.passages
        ]

    def text_branch(self, branch: str, question: str, playback=None) -> tuple[list[Hit], bool]:
        result = self.search(branch, question, playback)
        if result is None:
            return [], False
        return self.hits(result), result.relevant

    def frame_branch(self, question: str) -> list[Hit]:
        from harness.corpus import FRAME_PREFIX

        found = self.search(FRAMES, question)
        return [
            Hit(
                f"{FRAME_PREFIX}{hit.frame.id}",
                hit.frame.document_id,
                self.locator.locate(f"{FRAME_PREFIX}{hit.frame.id}"),
                _text_hash(hit.frame.text),
            )
            for hit in found
        ]


def variants() -> list[tuple[str, object]]:
    """Aday kıtlığı ve tekrar için denenen hibrit ayarları (#29); ilki üretimdeki ayardır."""
    from app.retrieval.hybrid import RetrievalParams

    production = RetrievalParams()
    return [
        ("üretim", production),
        ("aday 20", RetrievalParams(candidates_per_method=20)),
        ("aday 30", RetrievalParams(candidates_per_method=30)),
        ("aday 50", RetrievalParams(candidates_per_method=50)),
        ("doküman ≤2", RetrievalParams(max_per_document=2)),
        ("doküman ≤3", RetrievalParams(max_per_document=3)),
        ("aday 20, doküman ≤2", RetrievalParams(candidates_per_method=20, max_per_document=2)),
        ("aday 30, doküman ≤2", RetrievalParams(candidates_per_method=30, max_per_document=2)),
        ("aday 30, doküman ≤3", RetrievalParams(candidates_per_method=30, max_per_document=3)),
    ]


@dataclass
class VariantResult:
    name: str
    params: dict
    # Split → Recall@5 (oynatma konumsuz hibrit) ve oynatma konumlu hibrit.
    recall: dict[str, float | None]
    recall_playback: dict[str, float | None]
    items: dict[str, int]


def run_variants(probe: "CourseProbe", items: Sequence[GoldItem]) -> list[VariantResult]:
    """Her değişke aynı sorularda (k = 5) koşulur; Recall@5 split başına ayrı yazılır."""
    results = []
    for name, params in variants():
        plain: dict[str, list[Hit]] = {}
        played: dict[str, list[Hit]] = {}
        for item in items:
            plain[item.id] = probe.hits(probe.search_with(params, item.question))
            if item.playback is not None:
                result = probe.search_with(params, item.question, item.playback)
                if result is not None:
                    played[item.id] = probe.hits(result)
        groups = {
            "all": list(items),
            **{split.value: [i for i in items if i.split is split] for split in Split},
        }
        results.append(
            VariantResult(
                name=name,
                params=asdict(params),
                recall={key: _recall(group, plain) for key, group in groups.items()},
                recall_playback={
                    key: _recall([i for i in group if i.id in played], played)
                    for key, group in groups.items()
                },
                items={key: len(group) for key, group in groups.items()},
            )
        )
    return results


def _course_facts(db, course) -> dict:
    from sqlalchemy import func, select

    from app.db.models import Chunk, Document, VideoFrame

    documents = set(db.scalars(select(Document.id).where(Document.course_id == course.id)))
    chunks = db.scalar(select(func.count(Chunk.id)).where(Chunk.course_id == course.id)) or 0
    searchable_frames = (
        db.scalar(
            select(func.count(VideoFrame.id)).where(
                VideoFrame.course_id == course.id,
                VideoFrame.status.in_(("readable", "partial")),
            )
        )
        or 0
    )
    frame_rows = db.execute(
        select(
            VideoFrame.document_id,
            VideoFrame.ordinal,
            VideoFrame.t_start,
            VideoFrame.t_end,
            VideoFrame.t_frame,
            VideoFrame.status,
        ).where(VideoFrame.course_id == course.id)
    ).all()
    framed = {row[0] for row in frame_rows}
    durations = dict(
        db.execute(select(Document.id, Document.duration_s).where(Document.id.in_(framed))).all()
    )
    transcript: dict[int, list[tuple[float, float]]] = {}
    for document_id, start, end in db.execute(
        select(Chunk.document_id, Chunk.t_start, Chunk.t_end).where(
            Chunk.document_id.in_(framed), Chunk.t_start.is_not(None), Chunk.t_end.is_not(None)
        )
    ):
        transcript.setdefault(document_id, []).append((start, end))
    return {
        "documents": documents,
        "chunks": chunks,
        "searchable_frames": searchable_frames,
        "framed_videos": framed,
        "alignment": frame_alignment([tuple(r) for r in frame_rows], durations, transcript),
    }


def _frame_eligible(item: GoldItem, framed_shas: set[str]) -> bool:
    """Kare dalı yalnızca kanıtı karesi çıkarılmış bir videoda olan sorularda ölçülür."""
    return any(e.document_sha256 in framed_shas and e.t_start is not None for e in item.evidence)


def measure(args: argparse.Namespace) -> dict:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import settings
    from app.retrieval.index import frame_inventory, inventory
    from harness.corpus import CorpusError, Locator, corpus_fingerprint, find_course, snapshot
    from harness.fingerprint import file_sha256
    from harness.retrieval_sweep import _cached_embedder
    from harness.run import playback_documents

    split = None if args.split == "all" else Split(args.split)
    embedder = _cached_embedder()
    engine = create_engine(args.database_url or settings.database_url)
    courses: list[dict] = []
    gaps: list[str] = []
    loaded = []
    for gold_path in args.gold:
        gold = load_gold_set(gold_path)
        manifest_path = gold_path.parent / gold.manifest
        manifest = load_manifest(manifest_path)
        errors = structural_errors(gold, manifest)
        if errors:
            raise SystemExit(f"{gold_path}: gold set tutarsız:\n  " + "\n  ".join(errors))
        items, selection_gaps = select_items(gold.items, split, args.include_unreviewed)
        answerable = [i for i in items if i.kind is ItemKind.ANSWERABLE and i.evidence]
        loaded.append((gold_path, gold, manifest_path, manifest, answerable, selection_gaps))

    with Session(engine) as db:
        contexts = {}
        for gold_path, gold, manifest_path, manifest, answerable, selection_gaps in loaded:
            course = find_course(db, gold.course_code)
            locator = Locator(db, args.files_root)
            corpus = snapshot(db, course, manifest, locator)
            if corpus.unapproved_indexed:
                raise CorpusError(
                    f"{gold.course_code}: envanterde onaylı olmayan doküman indekste: "
                    + ", ".join(corpus.unapproved_indexed)
                )
            videos = playback_documents(db, course, locator)
            facts = _course_facts(db, course)
            framed_shas = {sha for sha, doc in videos.items() if doc in facts["framed_videos"]}
            contexts[gold.course_code] = (course, locator, videos, facts)
            probe = CourseProbe(db, course, locator, embedder, videos)

            hits: dict[str, dict[str, list[Hit]]] = {b: {} for b in BRANCHES}
            refused: list[str] = []
            for item in answerable:
                for branch in (HYBRID, DENSE, LEXICAL):
                    found, relevant = probe.text_branch(branch, item.question)
                    hits[branch][item.id] = found
                    if branch == HYBRID and not relevant:
                        refused.append(item.id)
                if item.playback is not None:
                    found, _ = probe.text_branch(PLAYBACK, item.question, item.playback)
                    hits[PLAYBACK][item.id] = found
                if _frame_eligible(item, framed_shas):
                    hits[FRAMES][item.id] = probe.frame_branch(item.question)

            branches = [
                summarize_branch(
                    branch,
                    answerable,
                    hits[branch],
                    facts["documents"],
                    facts["searchable_frames"] if branch == FRAMES else facts["chunks"],
                )
                for branch in BRANCHES
            ]
            compared = run_variants(probe, answerable)
            index = inventory(db, course.id)
            frames = frame_inventory(db, course.id)
            course_gaps = list(selection_gaps)
            course_gaps += [f"Eksik girdi: {m.what}" for m in manifest.missing_inputs]
            if any(not item.reviewed for item in answerable):
                course_gaps.append(
                    "Taslak set: eğitmen/TA incelemesi olmayan sorular ölçüldü; sayılar kabul "
                    "kanıtı değildir"
                )
            for branch in branches:
                if 0 < branch.items < MIN_ITEMS:
                    course_gaps.append(f"{branch.branch}: {branch.items} soru (küçük örnek)")
            if not hits[FRAMES]:
                course_gaps.append(
                    "Kare dalı ölçülmedi: kanıtı karesi çıkarılmış videoda olan soru yok"
                )
            if index.stale(embedder.identity):
                course_gaps.append(
                    f"{index.stale(embedder.identity)} parça etkin embedder'la vektörleştirilmemiş"
                )
            courses.append(
                {
                    "course_code": gold.course_code,
                    "gold_set": str(gold_path),
                    "gold_set_sha256": file_sha256(gold_path),
                    "manifest_sha256": file_sha256(manifest_path),
                    "fingerprints": {
                        "corpus": corpus_fingerprint(corpus),
                        "embedding_identity": embedder.identity,
                        "index": index.fingerprint,
                        "frames": frames.fingerprint,
                    },
                    "index": {
                        "documents": len(corpus.documents),
                        "chunks": index.chunks,
                        "chunks_by_embedding": {str(k): v for k, v in index.by_embedding.items()},
                        "frames": frames.frames,
                        "frames_by_status": frames.by_status,
                        "frame_extractors": frames.extractors,
                        "frame_interpreters": frames.interpreters,
                        "framed_videos": len(facts["framed_videos"]),
                    },
                    "questions": len(answerable),
                    "branches": [asdict(b) for b in branches],
                    "variants": [asdict(v) for v in compared],
                    "gate_refused": refused,
                    "frame_alignment": asdict(facts["alignment"]),
                    "gaps": course_gaps,
                    "_items": answerable,
                }
            )

        # Ders filtresi: her dersin soruları diğer derslerde sorulur; sonuçlar orada kalmalı.
        isolation = []
        for asked in courses:
            for other in courses:
                if other is asked:
                    continue
                course, locator, videos, facts = contexts[other["course_code"]]
                probe = CourseProbe(db, course, locator, embedder, videos)
                leaks = answered = 0
                for item in asked["_items"]:
                    for branch in (HYBRID, DENSE, LEXICAL):
                        found, _ = probe.text_branch(branch, item.question)
                        answered += bool(found)
                        leaks += sum(h.document_id not in facts["documents"] for h in found)
                    found = probe.frame_branch(item.question)
                    leaks += sum(h.document_id not in facts["documents"] for h in found)
                isolation.append(
                    {
                        "questions_from": asked["course_code"],
                        "asked_in": other["course_code"],
                        "questions": len(asked["_items"]),
                        "branches_with_results": answered,
                        "foreign_hits": leaks,
                    }
                )

        plans = []
        for entry in courses:
            if not entry["_items"]:
                continue
            course, locator, videos, facts = contexts[entry["course_code"]]
            probe = CourseProbe(db, course, locator, embedder, videos)
            sample = entry["_items"][0]
            playback_sample = next((i for i in entry["_items"] if i.playback), None)
            calls = [(HYBRID, sample.question, None), (FRAMES, sample.question, None)]
            if playback_sample is not None:
                calls.append((PLAYBACK, playback_sample.question, playback_sample.playback))
            for branch, question, playback in calls:
                # Üretimdeki k ile; aynı biçimdeki sorgular (ör. kare başına bağlam) bir kez.
                with captured_selects(engine) as statements:
                    probe.search(branch, question, playback, k=RECALL_K)
                repeats: dict[str, int] = {}
                unique: list[tuple[str, object]] = []
                for statement, parameters in statements:
                    if statement not in repeats:
                        unique.append((statement, parameters))
                    repeats[statement] = repeats.get(statement, 0) + 1
                for number, (statement, parameters) in enumerate(unique, start=1):
                    label = (
                        f"{entry['course_code']} {branch} #{number}: {_first_table(statement)}"
                        + (f" (×{repeats[statement]})" if repeats[statement] > 1 else "")
                    )
                    plans.append(asdict(summarize_plan(label, explain(db, statement, parameters))))
        db.rollback()

    for entry in courses:
        entry.pop("_items")
    commit, dirty = git_state(args.repo)
    if dirty:
        gaps.append("Çalışma ağacında commit'lenmemiş değişiklik var; ölçüm tam tekrarlanamaz")
    if any(plan["uses_vector_index"] for plan in plans):
        gaps.append("Bir sorgu HNSW indeksini kullandı: ders filtresiyle aday kaybı riski")
    if any(row["foreign_hits"] for row in isolation) or any(
        branch["foreign_hits"] for entry in courses for branch in entry["branches"]
    ):
        gaps.append("DERS FİLTRESİ İHLALİ: başka dersin sonucu döndü")
    return {
        "report_id": f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}_courses_{uuid.uuid4().hex[:6]}",
        "split": args.split,
        "git_commit": commit,
        "git_dirty": dirty,
        "recall_k": RECALL_K,
        "rank_depth": RANK_DEPTH,
        "courses": courses,
        "isolation": isolation,
        "plans": plans,
        "gaps": gaps,
    }


def _first_table(statement: str) -> str:
    """Sorgu etiketi: FROM'dan sonraki ilk tablo (plan tablosunda okunabilirlik için)."""
    words = statement.replace("\n", " ").split()
    for index, word in enumerate(words[:-1]):
        table = words[index + 1]
        if word.upper() == "FROM" and table.replace("_", "").isalnum():
            return table
    return "?"


# --- Rapor -------------------------------------------------------------------------------------


def pooled_variants(courses: Sequence[dict]) -> dict[str, dict[str, float | None]]:
    """Değişke başına derslerin Recall@5'i, soru sayısıyla ağırlıklı ortalama (split başına)."""
    keys = ("calibration", "heldout", "all")
    sums: dict[str, dict[str, list[float]]] = {}
    for entry in courses:
        for variant in entry.get("variants", []):
            row = sums.setdefault(variant["name"], {key: [0.0, 0.0] for key in keys})
            for key in keys:
                value, count = variant["recall"][key], variant["items"][key]
                if value is not None and count:
                    row[key][0] += value * count
                    row[key][1] += count
    return {
        name: {key: round(total / n, 4) if n else None for key, (total, n) in row.items()}
        for name, row in sums.items()
    }


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render_markdown(report: dict) -> str:
    lines = [
        f"# Çok dersli arama ölçümü `{report['report_id']}`",
        "",
        f"- Commit: `{report['git_commit'] or '?'}`"
        + (" (commit'lenmemiş değişiklik var)" if report["git_dirty"] else ""),
        f"- Split: `{report['split']}` · Recall@{report['recall_k']} · sıra derinliği "
        f"{report['rank_depth']}",
    ]
    for entry in report["courses"]:
        fp = entry["fingerprints"]
        index = entry["index"]
        lines += [
            "",
            f"## {entry['course_code']}",
            "",
            f"- Soru (kanıtlı, cevaplanabilir): {entry['questions']}",
            f"- İndeks: {index['documents']} doküman, {index['chunks']} parça, "
            f"{index['frames']} kare ({index['framed_videos']} video) {index['frames_by_status']}",
            f"- Parmak izleri: derlem `{fp['corpus'][:16]}` · embedder `{fp['embedding_identity']}`"
            f" · metin indeksi `{fp['index'][:16]}` · kareler `{fp['frames'][:16]}`",
            f"- Kare çıkarıcı: {', '.join(index['frame_extractors']) or '—'} · yorumlayıcı: "
            f"{', '.join(index['frame_interpreters']) or '—'}",
            "",
            "| Dal | Soru | Recall@5 | "
            + " | ".join(t.value for t in QueryType)
            + " | Kısa liste | Tekrarlı soru | Ders dışı |",
            "|---" * (6 + len(QueryType)) + "|",
        ]
        for branch in entry["branches"]:
            by_type = [
                f"{_fmt(branch['recall_by_type'][t.value])} ({branch['items_by_type'][t.value]})"
                for t in QueryType
            ]
            lines.append(
                f"| {branch['branch']} | {branch['items']} | {_fmt(branch['recall_at_5'])} | "
                + " | ".join(by_type)
                + f" | {len(branch['short_lists'])} | {len(branch['duplicates'])} | "
                f"{branch['foreign_hits']} |"
            )
        lines += [
            "",
            "Hibrit değişkeleri (Recall@5; kalibrasyon / held-out / tümü; oynatma konumlu tümü):",
            "",
            "| Değişke | Kalibrasyon | Held-out | Tümü | Oynatma konumlu |",
            "|---|---|---|---|---|",
        ]
        for variant in entry["variants"]:
            recall, items = variant["recall"], variant["items"]
            lines.append(
                f"| {variant['name']} | {_fmt(recall['calibration'])} ({items['calibration']}) | "
                f"{_fmt(recall['heldout'])} ({items['heldout']}) | {_fmt(recall['all'])} "
                f"({items['all']}) | {_fmt(variant['recall_playback']['all'])} |"
            )
        hybrid = next(b for b in entry["branches"] if b["branch"] == HYBRID)
        missed = {k: v for k, v in hybrid["first_hit_rank"].items() if v is None or v > 5}
        lines += [
            "",
            "- Hibritte ilk 5'te bulunamayan: "
            + (
                ", ".join(f"{k} (sıra {v or '>' + str(RANK_DEPTH)})" for k, v in missed.items())
                or "yok"
            ),
            f"- Kapıdan geçemeyen cevaplanabilir soru: {', '.join(entry['gate_refused']) or 'yok'}",
        ]
        alignment = entry["frame_alignment"]
        lines.append(
            f"- Kare hizası: {alignment['frames']} kare, {alignment['searchable']} aranabilir; "
            f"geçersiz aralık {alignment['invalid_interval']}, süre dışı "
            f"{alignment['beyond_duration']}, çakışan komşu {alignment['overlapping_neighbors']}, "
            f"transkriptsiz {alignment['without_transcript']}, boşluk toplamı "
            f"{alignment['gap_total_s']} sn"
        )
        if entry["gaps"]:
            lines += ["", "Boşluklar:", *[f"- {gap}" for gap in entry["gaps"]]]

    pooled = pooled_variants(report["courses"])
    if pooled:
        lines += [
            "",
            "## Değişkeler, iki ders birlikte (soru sayısıyla ağırlıklı Recall@5)",
            "",
            "| Değişke | Kalibrasyon | Held-out | Tümü |",
            "|---|---|---|---|",
            *[
                f"| {name} | {_fmt(row['calibration'])} | {_fmt(row['heldout'])} | "
                f"{_fmt(row['all'])} |"
                for name, row in pooled.items()
            ],
        ]
    lines += [
        "",
        "## Ders filtresi (çapraz sorular)",
        "",
        "| Soruların dersi | Sorulduğu ders | Soru | Sonuç dönen dal | Ders dışı sonuç |",
        "|---|---|---|---|---|",
    ]
    for row in report["isolation"]:
        lines.append(
            f"| {row['questions_from']} | {row['asked_in']} | {row['questions']} | "
            f"{row['branches_with_results']} | {row['foreign_hits']} |"
        )
    lines += [
        "",
        "## Sorgu planları",
        "",
        "| Sorgu | Düğümler | İndeksler | HNSW | Satır | Süre (ms) |",
        "|---|---|---|---|---|---|",
    ]
    for plan in report["plans"]:
        vector = "evet" if plan["uses_vector_index"] else "hayır"
        lines.append(
            f"| {plan['query']} | {', '.join(plan['node_types'])} | "
            f"{', '.join(plan['indexes']) or '—'} | {vector} | {plan['rows']} | "
            f"{_fmt(plan['execution_ms'])} |"
        )
    if report["gaps"]:
        lines += ["", "## Boşluklar", "", *[f"- {gap}" for gap in report["gaps"]]]
    return "\n".join(lines) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m harness.course_retrieval", description=__doc__)
    parser.add_argument("--gold", type=Path, nargs="+", required=True)
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
    report = measure(args)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{report['report_id']}.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, default=str)
    with path.with_suffix(".md").open("x", encoding="utf-8") as file:
        file.write(render_markdown(report))
    print(f"Ölçüm: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
