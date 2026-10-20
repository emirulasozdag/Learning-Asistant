from dataclasses import dataclass, field


@dataclass
class VideoPosition:
    """Öğrencinin izlediği video (doküman kimliği) ve durdurduğu an (saniye)."""

    document_id: int
    time_s: float


@dataclass
class RetrievedPassage:
    """Arama sonucu bir ders parçası. `source_id` alıntılarda kullanılan kimliktir (chunk id)."""

    source_id: str
    document_id: int
    document_title: str
    text: str
    score: float
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
    # Anlamsal benzerlik (kosinüs, 0–1); dense aramada bulunmadıysa None.
    dense_score: float | None = None
    # Kelime aramasındaki sıra (1 = en iyi); kelime eşleşmesi yoksa None.
    lexical_rank: int | None = None
    # Sorunun anahtar kelimelerinden bu parçada geçenlerin IDF ağırlıklı payı (0–1).
    keyword_coverage: float | None = None


@dataclass
class RetrievalResult:
    """Birleştirilmiş sonuç + sorunun dersle ilgili sayılıp sayılmadığı."""

    passages: list[RetrievedPassage] = field(default_factory=list)
    # Alakasızlık kapısı (bkz. `hybrid.retrieve`); False ise LLM çağrılmaz.
    relevant: bool = False
    # Sorunun kendisi için en iyi anlamsal benzerlik ve anahtar kelime kapsaması.
    best_similarity: float | None = None
    keyword_coverage: float | None = None
    # Soru tek başına kapıdan geçemedi, önceki soruyla birlikte geçti (eksik takip sorusu).
    admitted_by_context: bool = False
