from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation


class VideoRef(BaseModel):
    """Öğrencinin izlediği ders videosu ve durdurduğu an.

    `document_id`: videonun `Document` kimliği (zaman damgası değil, kimlik videoyu ayırt eder).
    `time_s`: videonun başından itibaren saniye.
    """

    document_id: int
    time_s: float = Field(ge=0)


class AskRequest(BaseModel):
    """Grounded Q&A isteği. video: öğrencinin izlediği video ve durdurduğu an (isteğe bağlı).

    Oynatma konumu önceliği henüz uygulanmadı (#14'ün sonraki PR'ları); alan kabul edilir.
    """

    course_id: int
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    video: VideoRef | None = None


class RetrievalHit(BaseModel):
    """“Nasıl bulundu” paneli: aramanın getirdiği bir parça ve skorları."""

    source_id: str
    document_title: str
    page: int | None = None
    # Video parçasında saniye cinsinden aralık (sayfa yerine).
    t_start: float | None = None
    t_end: float | None = None
    # Anlamsal benzerlik (0–1); anlamsal aramanın ilk adayları arasında değilse None.
    dense_score: float | None = None
    # Kelime aramasındaki sıra (1 = en iyi); kelime eşleşmesi yoksa None.
    lexical_rank: int | None = None
    # Cevapta alıntılandı mı?
    used: bool = False


# Cevabın nasıl sonuçlandığı (arayüz her birine farklı mesaj gösterebilir):
# - answered: doğrulanmış, alıntılı cevap (LLM ya da LLM'siz alıntı modu)
# - insufficient_evidence: materyalde yok (alakasızlık kapısı ya da model "YOK:" dedi)
# - unsupported: model cevap yazdı ama alıntı doğrulamasından geçemedi
# - model_refusal: model soruyu yanıtlamayı reddetti
# - provider_failure: LLM servisine ulaşılamadı; yerine en ilgili parça alıntılandı
# - verification_failure: [ekleme, #10] cevap üretildi ama iddia kontrolü yapılamadı (judge yok,
#   erişilemedi ya da sözleşme dışı çıktı); üretilen metin gösterilmez, en ilgili parça alıntılanır
AskOutcome = Literal[
    "answered",
    "insufficient_evidence",
    "unsupported",
    "model_refusal",
    "provider_failure",
    "verification_failure",
]


class ClaimCheck(BaseModel):
    """[ekleme, #10] İddia kontrolünün özeti. Ayrıntılı kayıt (atomik bilgiler, kararlar)
    mesaj meta'sında tutulur; öğrenciye yalnızca bu özet döner.

    status: checked (judge her iddiayı etiketledi) · not_configured (judge yok) · failed (judge
    hatası ya da sözleşme dışı çıktı) · off (CLAIM_CHECK=off; yalnızca alıntı doğrulaması).
    """

    status: Literal["checked", "not_configured", "failed", "off"]
    judge_model: str | None = None
    # Judge'a giden iddia sayısı ve desteklenmeyen bulunup cevaptan çıkarılanlar.
    claims: int = 0
    unsupported: int = 0
    # Denetim kaydı (iddia, alıntılanan kaynak kimlikleri, atomik bilgiler, karar, gerekçe, istem
    # sürümü). Mesaj meta'sına yazılır; API yanıtına girmez.
    records: list[dict] = Field(default_factory=list, exclude=True)
    prompt_version: str | None = None
    # Kontrol yapılamadıysa nedeni (log ve eğitmen için; öğrenciye gösterilmez).
    error: str | None = Field(default=None, exclude=True)


class AskResponse(BaseModel):
    """Cite-or-decline cevabı: ya alıntılı cevap ya da gerekçeli reddetme.

    `answer` içindeki [1], [2] işaretleri `citations` listesindeki sıraya karşılık gelir.
    mode: "llm" = model kaynaklardan cevap yazdı; "extractive" = LLM yok/erişilemedi,
    en ilgili parça alıntılandı.

    Akışta (`/ask/stream`) gelen `delta` metni taslaktır; yalnızca bu yanıt doğrulanmıştır
    ve taslağın yerini her zaman alır.
    """

    answer: str | None
    mode: Literal["llm", "extractive"] = "llm"
    outcome: AskOutcome = "answered"
    # Kaynağa dayanmadığı için cevaptan çıkarılan iddia (cümle) sayısı.
    unsupported_removed: int = 0
    # [ekleme] Kısmi cevapta kaynakların kapsamadığı kısım (modelin "EKSİK:" satırı); alıntısızdır.
    coverage_gap: str | None = None
    citations: list[Citation] = []
    declined: bool = False
    decline_reason: str | None = None
    suggested_sources: list[Citation] = []
    conversation_id: int | None = None
    retrieval: list[RetrievalHit] = []
    # Alakasızlık kapısı eşiği ve en iyi anlamsal benzerlik (panelde gösterilir).
    similarity_threshold: float | None = None
    best_similarity: float | None = None
    # Cevabı üreten model (LLM'siz modda None).
    model: str | None = None
    # [ekleme, #10] İddia kontrolü; model cevap yazmadıysa (ret, LLM'siz mod) None.
    claim_check: ClaimCheck | None = None
