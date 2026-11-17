from typing import Literal

from pydantic import BaseModel

from app.schemas.materials import MaterialType

# readable: okundu · partial: okundu, güveni düşük kelimeler var · unreadable: yazı var ama
# okunamadı · no_text: yazı bulunmadı (ör. fotoğraf, etiketsiz diyagram). Son ikisinde `text` boş.
FrameStatus = Literal["readable", "partial", "unreadable", "no_text"]


class Highlight(BaseModel):
    """Sayfa görüntüsü üzerinde alıntılanan satır; koordinatlar sayfaya oranla (0–1)."""

    x: float
    y: float
    width: float
    height: float


class SourceAlternative(BaseModel):
    """Video parçasıyla aynı içeriği taşıyan doküman parçası (#19): slayt, ders notu sayfası."""

    source_id: str
    document_id: int
    document_title: str
    material_type: MaterialType
    page: int | None = None
    # Video parçasına anlamsal benzerlik (kosinüs, 0–1).
    similarity: float


class FrameRef(BaseModel):
    """Ders videosundan çıkarılan kare (#24, ADR-10).

    Orijinal kanıt karenin görüntüsü (`image_url`) ve zamanıdır. `text` OCR'ın türettiği metindir,
    orijinal kanıt değildir; kontrol edilmeden cevapta kanıt olarak alıntılanmaz (#26).
    """

    frame_id: int
    document_id: int
    # Slaytın ekranda sabit kaldığı aralık ve görüntünün alındığı an (saniye).
    t_start: float
    t_end: float
    t_frame: float
    image_url: str
    status: FrameStatus
    text: str | None = None
    # Okunan kelimelerin ortalama OCR güveni (0–1).
    confidence: float | None = None
    # Metni türeten araç, ör. "tesseract/5.5.0/tur+eng".
    extractor: str


class SourceDetail(BaseModel):
    """Kaynak görüntüleyicide açılacak alıntı: metin + sayfa veya video anı."""

    source_id: str
    # Erişim kontrolü için (CONTRACTS.md §1, §3): kaynak yalnızca bu dersin üyelerine açılır.
    course_id: int
    document_id: int
    document_title: str
    material_type: MaterialType
    text: str
    page: int | None = None
    t_start: float | None = None
    t_end: float | None = None
    # Oynatılabilir ya da açılabilir opak URL. Video parçasında aralık `t_start`–`t_end`dir;
    # oynatıcı `t_start`a sarar (#22).
    media_url: str | None = None
    # Yalnızca PDF: sayfanın görüntüsü ve alıntılanan satırların yeri.
    page_image_url: str | None = None
    highlights: list[Highlight] = []
    # Yalnızca video parçası: aynı içeriğin dokümandaki karşılıkları (videoyu açamayan ya da
    # metinden okumak isteyen öğrenci için), en benzer önce. Diğer parçalarda boş.
    alternatives: list[SourceAlternative] = []
    # Yalnızca video parçası: parçanın aralığında ekranda olan kareler, zamana göre (#24).
    # Kare çıkarılmadıysa (altyazıyla yüklenen video, özellik kapalı) boş.
    frames: list[FrameRef] = []
