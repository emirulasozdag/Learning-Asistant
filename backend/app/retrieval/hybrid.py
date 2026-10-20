from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Course
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.retrieval.dense import dense_search
from app.retrieval.fusion import RRF_K, reciprocal_rank_fusion
from app.retrieval.lexical import lexical_search
from app.retrieval.types import RetrievalResult, RetrievedPassage, VideoPosition

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

    `video`: oynatma konumu önceliği sonraki PR'da (#14 c); şimdilik yok sayılır.

    Sonraki adımlar: video-zaman önceliği (`video_time.py`); rerank ölçülen fayda olmadığı
    için kapalı (`rerank.py`).
    """
    params = (params or RetrievalParams()).resolved()
    embedder = embedder or get_embedder()
    current = _search(db, course, query, embedder, params)
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

    return RetrievalResult(
        passages=reciprocal_rank_fusion(rankings, k=params.rrf_k, weights=weights)[:k],
        relevant=relevant,
        best_similarity=current.best_similarity,
        keyword_coverage=current.keyword_coverage,
        admitted_by_context=admitted_by_context,
    )


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
