import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, Document
from app.retrieval.frames import frames_overlapping
from app.retrieval.types import RetrievedPassage, VideoPosition


def video_neighbors(
    db: Session, course: Course, video: VideoPosition, window_s: float, limit: int
) -> list[RetrievedPassage]:
    """Videonun durdurulan ana yakın parçaları: 'bu adım' soruları için yumuşak öncelik girdisi.

    Yalnızca aynı dersin ve aynı videonun (`document_id`) zaman aralığı
    [time_s - window_s, time_s + window_s] ile örtüşen parçaları döner; başka videonun aynı
    saniyesi karışmaz. Sıra, parçanın orta noktasının `time_s`e uzaklığıdır (yakın önce).
    """
    midpoint = (Chunk.t_start + Chunk.t_end) / 2
    rows = db.execute(
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.document_id == video.document_id,
            Chunk.course_id == course.id,
            Document.course_id == course.id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
            Chunk.t_start.is_not(None),
            Chunk.t_end.is_not(None),
            Chunk.t_start <= video.time_s + window_s,
            Chunk.t_end >= video.time_s - window_s,
        )
        .order_by(func.abs(midpoint - video.time_s), Chunk.id)
        .limit(limit)
    )
    return [
        RetrievedPassage(
            source_id=str(chunk.id),
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=0.0,
            page=chunk.page,
            t_start=chunk.t_start,
            t_end=chunk.t_end,
        )
        for chunk, title in rows
    ]


# "Burası", "bu kısım", "anlamadım" gibi: sorunun konusu sözcüklerde değil, durdurulan andadır.
_DEICTIC = re.compile(
    r"\b(bura\w*|şura\w*|bu\s+(kısım|kısmı|kısmını|adım|adımı|adımda|bölüm|bölümü|slayt|slaytı|"
    r"anlattığı|anlatılan|dediği|söylediği|yaptığı|yazdığı|örnek|örneği|örnekte|"
    r"formül|formülü|kod|kodu|çizim|çizimi|şekil|şekli|tahta|tahtadaki)|"
    r"bunu|bunlar\w*|şunu|şimdi\s+anlat\w*|hoca\w*\s+(ne|neden|niye|nasıl)|anlamadım|anlayamadım|"
    r"here|this\s+(part|step|bit|slide|example|formula|code|line)|what\s+(he|she)\s+(said|means)|"
    r"explain\s+this|i\s+(don't|do\s+not|didn't)\s+(get|understand))\b",
    re.IGNORECASE,
)
_WORD = re.compile(r"\w+", re.UNICODE)
# Konu taşımayan soru sözcükleri: yalnızca bunlardan oluşan soru ("neden?", "nasıl yani?") da
# durdurulan anı sorar.
_GENERIC = {
    "neden",
    "niye",
    "nasıl",
    "ne",
    "yani",
    "peki",
    "açıkla",
    "açıklar",
    "mısın",
    "misin",
    "anlat",
    "anlatır",
    "tekrar",
    "daha",
    "basit",
    "why",
    "how",
    "what",
    "explain",
    "again",
    "please",
    "lütfen",
}


def is_deictic(question: str) -> bool:
    """Soru durdurulan ana mı işaret ediyor ("burayı anlamadım", "bu adımı açıklar mısın")?

    İşaret sözcüğü varsa ya da soru yalnızca konu taşımayan sözcüklerden oluşuyorsa evet: bu
    sorular kendi sözcükleriyle aranırsa başka dokümanların genel eşleşmeleri öne çıkar (#102).
    "Dijkstra nedir?" gibi kısa ama konulu sorular işaret sayılmaz.
    """
    if _DEICTIC.search(question):
        return True
    words = [word.casefold() for word in _WORD.findall(question)]
    return bool(words) and all(word in _GENERIC for word in words)


def video_window(
    db: Session,
    course: Course,
    video: VideoPosition,
    before_s: float,
    after_s: float,
    limit: int,
) -> list[RetrievedPassage]:
    """Durdurulan anda anlatılan bölüm: [time_s - before_s, time_s + after_s] ile örtüşen
    transkript parçalarından ana en yakın `limit` tanesi, zaman sırasıyla (#102).

    Öğrenci çoğunlukla az önce duyduğunu sorar; bu yüzden uzaklık, anın biraz öncesine göre
    ölçülür. Başka dersin ya da hazır olmayan videonun parçası gelmez (`video_neighbors` gibi).
    """
    anchor = video.time_s - min(before_s, 20.0)
    midpoint = (Chunk.t_start + Chunk.t_end) / 2
    rows = db.execute(
        select(Chunk, Document.title)
        .join(Document, Document.id == Chunk.document_id)
        .where(
            Chunk.document_id == video.document_id,
            Chunk.course_id == course.id,
            Document.course_id == course.id,
            Document.approved_at.is_not(None),
            Document.status == "ready",
            Chunk.t_start.is_not(None),
            Chunk.t_end.is_not(None),
            Chunk.t_start <= video.time_s + after_s,
            Chunk.t_end >= video.time_s - before_s,
        )
        .order_by(func.abs(midpoint - anchor), Chunk.id)
        .limit(limit)
    ).all()
    passages = [
        RetrievedPassage(
            source_id=str(chunk.id),
            document_id=chunk.document_id,
            document_title=title,
            text=chunk.text,
            score=0.0,
            page=chunk.page,
            t_start=chunk.t_start,
            t_end=chunk.t_end,
        )
        for chunk, title in rows
    ]
    return sorted(passages, key=lambda passage: passage.t_start or 0.0)


def window_frame_text(
    db: Session, course: Course, document_id: int, t_start: float, t_end: float
) -> str:
    """Pencerede ekranda olan slaytların OCR metni (#24/#100), yalnızca dersin karelerinden.
    Yalnızca aramayı yönlendirmek için kullanılır; cevapta kanıt olmaz (ADR-10)."""
    frames = frames_overlapping(db, document_id, t_start, t_end, course_id=course.id)
    return "\n".join(frame.text for frame in frames if frame.text)
