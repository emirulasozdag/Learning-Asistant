"""AI Tutor sözleşmesi (ADR-7): bir tur = öğrenci mesajı → arayüz blokları.

Öğrenciye giden her içerik bir araçtan gelir ve kökenini (`provenance`) taşır:
- `course_answer`: ders materyalinden, alıntılı ve doğrulanmış cevap ya da gerekçeli ret.
  İçi `/ask` ile aynı `AskResponse`; arayüz aynı bileşenleri kullanabilir.
- `general_explanation`: ders materyalinde yok; genel bilgi, alıntısız, her zaman etiketli.
- `practice`: ders parçasına bağlı, otomatik kontrollerden geçmiş pratik sorusu (anahtarsız);
  cevap `POST /practice/{id}/answer` ile gönderilir.
- `clarification`: orkestratörün netleştirme sorusu (öğretim içeriği değildir).
- `notice`: sabit metinli bilgilendirme (selamlaşma, dersle ilgisiz, not verilen iş, hata).
- `follow_ups`: sonraki adım önerileri; metinleri sabittir, tıklanınca yeni tur olarak gider.
Orkestratörün serbest metni öğrenciye hiç gitmez.

Akışta (`/tutor/turn/stream`) gelen `delta` metinleri taslaktır; `block` olayındaki blok
taslağın yerini her zaman alır.
"""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.schemas.ask import AskResponse, VideoRef
from app.schemas.practice import PracticeItem

GENERAL_NOTICE = (
    "Bu açıklama ders materyalinden değil, genel bilgidir. Dersin anlatımıyla farklılık "
    "olursa ders materyali ve eğitmen esastır."
)


class CourseAnswerBlock(BaseModel):
    type: Literal["course_answer"] = "course_answer"
    provenance: Literal["course"] = "course"
    response: AskResponse


class GeneralExplanationBlock(BaseModel):
    type: Literal["general_explanation"] = "general_explanation"
    provenance: Literal["general"] = "general"
    text: str
    # Bağımsız doğrulama (#10, farklı model ailesinden judge) gelene kadar "unchecked".
    check: Literal["unchecked", "checked"] = "unchecked"
    notice: str = GENERAL_NOTICE
    model: str | None = None


class PracticeBlock(BaseModel):
    type: Literal["practice"] = "practice"
    provenance: Literal["course"] = "course"
    item: PracticeItem


class ClarificationBlock(BaseModel):
    type: Literal["clarification"] = "clarification"
    provenance: Literal["none"] = "none"
    question: str = Field(max_length=300)
    options: list[str] = Field(default=[], max_length=4)


# greeting: selam/teşekkür · off_topic: dersle ilgisiz · graded_work: not verilen ödev/sınav
# cevabı isteği · not_covered: materyalde yok (genel bilgi kapalı ya da verilemedi)
# · unavailable: istenen yetenek henüz yok · failure: tur tamamlanamadı
NoticeKind = Literal[
    "greeting", "off_topic", "graded_work", "not_covered", "unavailable", "failure"
]


class NoticeBlock(BaseModel):
    type: Literal["notice"] = "notice"
    provenance: Literal["none"] = "none"
    kind: NoticeKind
    text: str


FollowUpAction = Literal["simpler", "example"]


class FollowUp(BaseModel):
    action: FollowUpAction
    label: str
    # Tıklanınca yeni tur olarak gönderilecek mesaj.
    message: str


class FollowUpsBlock(BaseModel):
    type: Literal["follow_ups"] = "follow_ups"
    provenance: Literal["none"] = "none"
    items: list[FollowUp]


TutorBlock = Annotated[
    CourseAnswerBlock
    | GeneralExplanationBlock
    | PracticeBlock
    | ClarificationBlock
    | NoticeBlock
    | FollowUpsBlock,
    Field(discriminator="type"),
]


class TutorTurnRequest(BaseModel):
    course_id: int
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    # Öğrencinin izlediği video ve durdurduğu an; `answer_from_course` aracına geçer.
    video: VideoRef | None = None


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, Any] = {}
    # Aracın orkestratöre bildirdiği sonuç: answered, not_covered, rejected, failed...
    status: str
    duration_ms: int


class UsageRecord(BaseModel):
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    thought_tokens: int = 0
    cached_tokens: int = 0
    # Tahmini maliyet (`llm/catalog.py`); fiyatı bilinmeyen modelde None.
    cost_usd: float | None = None


class TurnTrace(BaseModel):
    """Turun nasıl yürüdüğü: değerlendirme ve hata ayıklama için (öğrenci arayüzünde gizli)."""

    # orchestrated: model araç seçti · direct: orkestratör yok/başarısız, sabit akış kullanıldı
    mode: Literal["orchestrated", "direct"]
    orchestrator_model: str | None = None
    fallback_reason: str | None = None
    steps: list[ToolTrace] = []
    usage: list[UsageRecord] = []
    cost_usd: float | None = None


class TutorTurnResponse(BaseModel):
    conversation_id: int
    blocks: list[TutorBlock]
    trace: TurnTrace
