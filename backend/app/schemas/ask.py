from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Citation, DbId
from app.schemas.sources import FrameRef


class VideoRef(BaseModel):
    """Öğrencinin izlediği ders videosu ve durdurduğu an.

    `document_id`: videonun `Document` kimliği (zaman damgası değil, kimlik videoyu ayırt eder).
    `time_s`: videonun başından itibaren saniye. Sonlu olmalı (`inf`/`nan` 422); süreyi aşan
    değer hata değildir, sunucu videonun süresine kırpar.
    `frame_id`: [ekleme, #25] öğrencinin baktığı kare (`FrameRef.frame_id`). Sunucu karenin bu
    videoya ait olduğunu ve `time_s` anında ekranda olduğunu doğrular (değilse 422
    `invalid_frame`). Verilmezse sunucu o anda ekrandaki kareyi seçer (kare yoksa boş kalır).
    """

    document_id: DbId
    time_s: float = Field(ge=0, allow_inf_nan=False)
    frame_id: DbId | None = None


class AskRequest(BaseModel):
    """Grounded Q&A isteği. video: öğrencinin izlediği video ve durdurduğu an (isteğe bağlı).

    Video verilirse durdurulan anın bölümü cevabın başına sabitlenir (#102) ve doğrulanmış
    bağlam (`AskResponse.video_context`) mesaj kaydına yazılır (#25).
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
    # [ekleme, #102] Öğrencinin durdurduğu andaki video bölümünden mi (cevabın başına sabitlenir)?
    video_moment: bool = False


# Cevabın nasıl sonuçlandığı (arayüz her birine farklı mesaj gösterebilir):
# - answered: doğrulanmış, alıntılı cevap (LLM ya da LLM'siz alıntı modu)
# - insufficient_evidence: materyalde yok (alakasızlık kapısı ya da model "YOK:" dedi)
# - unsupported: model cevap yazdı ama alıntı doğrulamasından geçemedi
# - model_refusal: model soruyu yanıtlamayı reddetti
# - provider_failure: LLM servisine ulaşılamadı; yerine en ilgili parça alıntılandı
# - verification_failure: [ekleme, #10] cevap üretildi ama iddia kontrolü yapılamadı (judge yok,
#   erişilemedi ya da sözleşme dışı çıktı); üretilen metin gösterilmez, en ilgili parça alıntılanır
# - needs_clarification: [ekleme, #26] videodaki sahne belirsiz; cevap yerine öğrenciye bir
#   netleştirme sorusu sorulur (`decline_reason`, `declined = true`). Yalnızca kare verildiğinde.
AskOutcome = Literal[
    "answered",
    "insufficient_evidence",
    "unsupported",
    "model_refusal",
    "provider_failure",
    "verification_failure",
    "needs_clarification",
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


class VideoMomentOut(BaseModel):
    """[ekleme, #102] Cevabın dayandığı, öğrencinin durdurduğu andaki video bölümü."""

    document_id: int
    document_title: str
    t_start: float
    t_end: float
    # Soru o anı işaret ediyordu ("burayı anlamadım"); arama o bölümün metniyle yapıldı.
    deictic: bool = False


class VideoContextOut(BaseModel):
    """[ekleme, #25] İsteğin doğrulanmış video bağlamı: hangi video varlığı, hangi an, hangi kare.

    Yalnızca istekte `video` verildiyse dolar. `time_s` videonun süresine kırpılmış konumdur;
    `frame` o anda ekrandaki (ya da öğrencinin seçtiği) karedir, kare çıkarılmadıysa None.
    Karenin `text`/`description` alanları türetilmiştir; kanıt kuralları #26'dadır.
    """

    document_id: int
    # Medya dosyasının SHA-256 özeti (altyazıyla yüklenen videoda None).
    media_sha256: str | None = None
    duration_s: float | None = None
    time_s: float
    frame: FrameRef | None = None


class FrameTrace(BaseModel):
    """[ekleme, #26] Kayıttaki bir kare: kimlik ve zaman (saniye). Görüntü ve OCR metni yok."""

    frame_id: int
    document_id: int
    t_start: float
    t_end: float
    t_frame: float


class VisualTrace(BaseModel):
    """[ekleme, #26, ADR-12] Görsel kanıtın denetim kaydı (asistan mesajının `meta.visual`'ı).

    `frames`: üreticiye verilen kareler (türetilmiş metin ve konuşmayla; görüntü üreticiye
    gitmez). `judge_images`: görüntüsü judge'a gönderilen karelerin kimlikleri. `cited`: cevapta
    kalan kare alıntılarının kimlikleri. Yalnızca kimlikler ve zamanlar; görüntü baytı, OCR metni
    ve betimleme kayda girmez.
    """

    frames: list[FrameTrace]
    judge_images: list[int] = Field(default_factory=list)
    cited: list[int] = Field(default_factory=list)


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
    # [ekleme, #102] Video durdurulmuşsa cevabın başına sabitlenen bölüm; yoksa None.
    video_moment: VideoMomentOut | None = None
    # [ekleme, #25] İstekte video verildiyse doğrulanmış video bağlamı; yoksa None.
    video_context: VideoContextOut | None = None
    # [ekleme, #26] Cevaba kare girdiyse görsel kanıtın kaydı; mesaj meta'sına yazılır, API
    # yanıtına girmez. Kare verilmeyen cevapta None.
    visual: VisualTrace | None = Field(default=None, exclude=True)
