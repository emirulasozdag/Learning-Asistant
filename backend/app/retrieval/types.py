from dataclasses import dataclass, field


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


@dataclass
class RetrievalResult:
    """Birleştirilmiş sonuç + sorunun dersle ilgili sayılıp sayılmadığı."""

    passages: list[RetrievedPassage] = field(default_factory=list)
    # Alakasızlık kapısı: hiç kelime eşleşmesi yok ve anlamsal benzerlik eşiğin altındaysa False.
    relevant: bool = False
    best_similarity: float | None = None
