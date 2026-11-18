from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.retrieval.dense import dense_search
from app.retrieval.fusion import RRF_K, reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.types import RetrievalResult, RetrievedPassage, VideoMoment, VideoPosition
from app.retrieval.video_time import is_deictic, video_neighbors, video_window, window_frame_text

# Her yöntemden alınan aday sayısı; RRF sonrası ilk `k` tanesi kullanılır.
CANDIDATES_PER_METHOD = 10
# Takip sorusunda önceki soruyla birlikte yapılan aramanın ağırlığı (yeni soru = 1).
CONTEXT_WEIGHT = 0.5

DENSE = "dense"
LEXICAL = "lexical"


@dataclass(frozen=True)
class RetrievalParams:
    """Arama ayarları. Varsayılanlar üretimdekidir; değerlendirme aracı karşılaştırmada değiştirir.

    Eşikler None ise ayarlardan (`settings.retrieval_*`) okunur.
    """

    methods: tuple[str, ...] = (DENSE, LEXICAL)
    candidates_per_method: int = CANDIDATES_PER_METHOD
    rrf_k: int = RRF_K
    context_weight: float = CONTEXT_WEIGHT
    # Oynatma konumu önceliği: durdurulan anın ±video_window_s saniyesindeki parçalar RRF'e ayrı
    # bir sıralama olarak video_weight ağırlığıyla girer (0 = kapalı). Eval'de kalibre edilecek.
    video_window_s: float = 120.0
    video_weight: float = 0.5
    # Durdurulan anın bölümü (#102): anın şu kadar öncesi ve sonrası, en çok şu kadar parça
    # cevabın başına sabitlenir. 0 parça = kapalı (yalnızca yumuşak öncelik).
    moment_before_s: float = 90.0
    moment_after_s: float = 20.0
    moment_chunks: int = 3
    min_similarity: float | None = None
    min_keyword_coverage: float | None = None
    follow_up_min_similarity: float | None = None

    def resolved(self) -> "RetrievalParams":
        return replace(
            self,
            min_similarity=_default(self.min_similarity, settings.retrieval_min_similarity),
            min_keyword_coverage=_default(
                self.min_keyword_coverage, settings.retrieval_min_keyword_coverage
            ),
            follow_up_min_similarity=_default(
                self.follow_up_min_similarity, settings.retrieval_follow_up_min_similarity
            ),
        )


def _default(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


@dataclass
class _Signals:
    rankings: list[list[RetrievedPassage]]
    best_similarity: float | None
    keyword_coverage: float | None

    def relevant(self, params: RetrievalParams) -> bool:
        assert params.min_similarity is not None and params.min_keyword_coverage is not None
        by_meaning = (
            self.best_similarity is not None and self.best_similarity >= params.min_similarity
        )
        by_keywords = (
            self.keyword_coverage is not None
            and self.keyword_coverage >= params.min_keyword_coverage
        )
        return by_meaning or by_keywords


def retrieve(
    db: Session,
    course: Course,
    query: str,
    video: VideoPosition | None = None,
    k: int = 5,
    embedder: Embedder | None = None,
    context: str | None = None,
    params: RetrievalParams | None = None,
) -> RetrievalResult:
    """Hibrit arama: anlamsal (e5 + pgvector) ve kelime (PostgreSQL FTS) → RRF → ilk k.

    Alakasızlık kapısı: en iyi anlamsal benzerlik `min_similarity` ya da en iyi parçanın
    anahtar kelime kapsaması `min_keyword_coverage` üstündeyse soru dersle ilgili sayılır.
    Tek bir ortak kelime ("time", "what") artık yetmez: kapsama IDF ağırlıklıdır.

    `context` (takip sorusunda önceki soru) verilirse soru bir de onunla birlikte aranır;
    "peki karmaşıklığı ne?" gibi eksik sorular anlaşılır, ama sıralamada yeni soru önde kalır.
    Kapı önce yeni soruya tek başına bakar. Geçemezse önceki soruyla birlikte geçmesi yalnızca
    yeni soru da derse yakınsa (benzerlik >= `follow_up_min_similarity`) kabul edilir: konu
    değiştiren alakasız bir soru, önceki sorunun eşleşmeleriyle içeri sızmaz.

    `video`: öğrencinin izlediği video ve durdurduğu an. Verilirse, o videonun durdurulan ana
    yakın parçaları (`video_neighbors`) RRF'e ayrı bir sıralama olarak `video_weight` ağırlığıyla
    eklenir: pencere içindeki parça sıralamada yukarı çıkar, ama hiçbir parça elenmez; pencere
    dışındaki kanıt ve diğer videolar yine bulunur. Alakasızlık kapısı videodan etkilenmez, yalnızca
    soru metninden hesaplanır.

    Durdurulan anın bölümü (#102): videonun durdurulan andan biraz öncesini kapsayan transkript
    parçaları (`video_window`) her zaman sonuçların başına sabitlenir; öğrenci çoğunlukla o anda
    anlatılanı sorar. "Burayı anlamadım" gibi o anı işaret eden sorular (`is_deictic`) o bölümün
    metniyle aranır ve kapıdan geçer; konulu sorular eskisi gibi kendi sözcükleriyle aranır.

    Rerank ölçülen fayda olmadığı için kapalı (`rerank.py`).
    """
    params = (params or RetrievalParams()).resolved()
    embedder = embedder or get_embedder()
    moment = _video_moment(db, course, video, params)
    deictic = moment is not None and is_deictic(query)
    search_text = query
    if deictic:
        # "Burayı anlamadım": konu sözcüklerde değil, o anda anlatılandadır. Arama o bölümün
        # transkripti (ve varsa slayt yazısı) ile yapılır; ilgili doküman sayfaları da bulunur.
        assert moment is not None
        frame_text = window_frame_text(db, moment.document_id, moment.t_start, moment.t_end)
        search_text = "\n".join(
            part for part in (query, _moment_text(moment.passages), frame_text) if part
        )
    current = _search(db, course, search_text, embedder, params)
    rankings = list(current.rankings)
    weights = [1.0] * len(rankings)
    relevant = current.relevant(params)
    admitted_by_context = False
    if context:
        combined = _search(db, course, f"{context}\n{query}", embedder, params)
        rankings += combined.rankings
        weights += [params.context_weight] * len(combined.rankings)
        if not relevant and combined.relevant(params):
            assert params.follow_up_min_similarity is not None
            near_course = (
                current.best_similarity is not None
                and current.best_similarity >= params.follow_up_min_similarity
            )
            relevant = admitted_by_context = near_course

    if video is not None and params.video_weight > 0:
        neighbors = video_neighbors(
            db, course, video, params.video_window_s, params.candidates_per_method
        )
        if neighbors:
            rankings.append(neighbors)
            weights.append(params.video_weight)

    fused = reciprocal_rank_fusion(rankings, k=params.rrf_k, weights=weights)
    if moment is None:
        return RetrievalResult(
            passages=fused[:k],
            relevant=relevant,
            best_similarity=current.best_similarity,
            keyword_coverage=current.keyword_coverage,
            admitted_by_context=admitted_by_context,
        )
    # Durdurulan andaki bölüm cevabın ilk kaynaklarıdır; diğer dokümanlar ardından gelir.
    pinned_ids = {passage.source_id for passage in moment.passages}
    rest = [passage for passage in fused if passage.source_id not in pinned_ids][:k]
    return RetrievalResult(
        passages=moment.passages + rest,
        # O anı işaret eden soru, o bölüm kanıt olduğu için kapıdan geçer.
        relevant=relevant or deictic,
        best_similarity=current.best_similarity,
        keyword_coverage=current.keyword_coverage,
        admitted_by_context=admitted_by_context,
        video_moment=VideoMoment(
            document_id=moment.document_id,
            document_title=moment.passages[0].document_title,
            t_start=moment.t_start,
            t_end=moment.t_end,
            source_ids=[passage.source_id for passage in moment.passages],
        ),
        deictic=deictic,
    )


@dataclass
class _Moment:
    document_id: int
    t_start: float
    t_end: float
    passages: list[RetrievedPassage]


def _video_moment(
    db: Session, course: Course, video: VideoPosition | None, params: RetrievalParams
) -> _Moment | None:
    if video is None or params.moment_chunks <= 0:
        return None
    passages = video_window(
        db, course, video, params.moment_before_s, params.moment_after_s, params.moment_chunks
    )
    if not passages:
        return None
    return _Moment(
        document_id=video.document_id,
        t_start=min(p.t_start for p in passages if p.t_start is not None),
        t_end=max(p.t_end for p in passages if p.t_end is not None),
        passages=passages,
    )


def _moment_text(passages: list[RetrievedPassage], limit: int = 1500) -> str:
    """Bölümün transkripti, embedder'ın girdi sınırını zorlamayacak uzunlukta."""
    return " ".join(passage.text for passage in passages)[:limit]


def _search(
    db: Session, course: Course, text: str, embedder: Embedder, params: RetrievalParams
) -> _Signals:
    rankings: list[list[RetrievedPassage]] = []
    best_similarity = keyword_coverage = None
    if DENSE in params.methods:
        dense = dense_search(
            db, course, embedder.embed_query(text), params.candidates_per_method, embedder.identity
        )
        rankings.append(dense)
        best_similarity = max(
            (p.dense_score for p in dense if p.dense_score is not None), default=None
        )
    if LEXICAL in params.methods:
        lexical = lexical_search(db, course, text, params.candidates_per_method)
        rankings.append(lexical)
        keyword_coverage = max(
            (p.keyword_coverage for p in lexical if p.keyword_coverage is not None), default=None
        )
    return _Signals(rankings, best_similarity, keyword_coverage)
