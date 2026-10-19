from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation


class AskRequest(BaseModel):
    """Grounded Q&A isteği. video_time_s: öğrencinin videoyu durdurduğu an (saniye)."""

    course_id: int
    question: str = Field(min_length=1, max_length=2000)
    video_time_s: float | None = None
    conversation_id: int | None = None


class RetrievalHit(BaseModel):
    """“Nasıl bulundu” paneli: aramanın getirdiği bir parça ve skorları."""

    source_id: str
    document_title: str
    page: int | None = None
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
AskOutcome = Literal[
    "answered", "insufficient_evidence", "unsupported", "model_refusal", "provider_failure"
]


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
