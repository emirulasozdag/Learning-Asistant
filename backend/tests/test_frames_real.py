"""Video kareleri uçtan uca: gerçek MP4 + gerçek Tesseract (#24, ADR-10).

Ders videosu testte PDF slaytlarından üretilir (`video_factory`); konuşma sahte transkriptörden
gelir. Yükleme API'si → kuyruk işi → kare çıkarma → OCR → veritabanı → arama ve kaynak
görüntüleyici zinciri gerçek bileşenlerle çalışır. `av` ve `tesseract` yalnızca Docker
imajındadır; yoksa (CI) bu dosya atlanır.
"""

import shutil
import struct
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document, VideoFrame
from app.embeddings.fake import FakeEmbedder
from app.ingestion.frames import extract_frames
from app.ingestion.ocr import read_image
from app.ingestion.types import RawSegment
from app.jobs.worker import run_pending
from app.retrieval.frames import frame_search
from tests.conftest import session_factory
from tests.test_transcription import FakeTranscriber, refreshed

pytest.importorskip("av", reason="PyAV yalnızca Docker imajında")
if shutil.which("tesseract") is None:
    pytest.skip("Tesseract yalnızca Docker imajında", allow_module_level=True)

from tests.video_factory import Slide, make_lecture_video  # noqa: E402 (av'den sonra)

FORMULA = "T(n) = T(n/2) + O(1)"
CODE = "if a[mid] == x: return mid"
# (başlangıç, bitiş, slayt); gerçek ekran zamanları.
LECTURE = [
    (0, 6, Slide(6, "Ikili Arama", ["mid = (lo + hi) // 2", FORMULA])),
    (6, 12, Slide(6, "Kod", ["while lo <= hi:", "    " + CODE], webcam=True)),
    (12, 18, Slide(6, "Dijkstra", diagram=("Kaynak", "Kuyruk", "Hedef"))),
    (18, 21, Slide(3, moving=True)),
    (21, 24, Slide(3, background=0.96)),
]
# Konuşma slaytlardaki her şeyi söylemez: "Kaynak" ve formül yalnızca ekrandadır.
SPEECH = [
    RawSegment(text="ikili arama her adimda araligi ikiye boler", t_start=0.5, t_end=5.5),
    RawSegment(text="bu dongu hedefi bulunca durur", t_start=6.5, t_end=11.5),
    RawSegment(text="dijkstra en kisa yolu bulur ve bir kuyruk kullanir", t_start=12.5, t_end=17.5),
]


@pytest.fixture
def lecture_video(tmp_path: Path) -> Path:
    return make_lecture_video(tmp_path / "ders.mp4", [slide for _, _, slide in LECTURE])


@pytest.fixture
def process(api, db: Session, db_engine, monkeypatch: pytest.MonkeyPatch):
    """Medyayı yükler ve işi gerçek kare adımıyla (sahte konuşma) çalıştırır."""
    monkeypatch.setattr(settings, "transcription_model", "tiny")
    monkeypatch.setattr(settings, "frame_extraction", "ocr")

    def run(client: TestClient, course: Course, name: str, content: bytes) -> Document:
        response = client.post(
            f"/courses/{course.id}/materials",
            data={"material_type": "video", "declaration": "true", "title": "Ders 5"},
            files={"file": (name, content)},
        )
        assert response.status_code == 201, response.text
        db.commit()
        transcriber = FakeTranscriber(segments=SPEECH, duration_s=24.0)
        assert run_pending(session_factory(db_engine), transcriber, FakeEmbedder()) == 1
        return refreshed(db, response.json()["id"])

    return run


def frames_of(db: Session, document: Document) -> list[VideoFrame]:
    db.expire_all()
    return list(
        db.scalars(
            select(VideoFrame)
            .where(VideoFrame.document_id == document.id)
            .order_by(VideoFrame.ordinal)
        )
    )


def test_lecture_video_slides_are_extracted_read_and_found(
    client: TestClient, db: Session, course: Course, process, lecture_video: Path
) -> None:
    document = process(client, course, "ders.mp4", lecture_video.read_bytes())

    assert document.status == "ready"
    frames = frames_of(db, document)
    # Üç slayt ve boş ekran; hareketli bölümden kare yok.
    assert len(frames) == 4
    expected = [(0, 6), (6, 12), (12, 18), (21, 24)]
    for frame, (start, end) in zip(frames, expected, strict=True):
        # Kamera kutusu ilk saniyelerde öğrenilir; başlangıç en çok 1,5 sn gecikir.
        assert start <= frame.t_start <= start + 1.5, frame.t_start
        assert abs(frame.t_end - end) <= 0.5, frame.t_end
        assert frame.t_start <= frame.t_frame <= frame.t_end
        assert frame.extractor.startswith("tesseract/") and frame.extractor.endswith("/tur+eng")
    formula, code, diagram, blank = frames
    assert formula.status == "readable" and FORMULA in formula.text
    assert "mid = (lo + hi) // 2" in formula.text
    # Koddaki `a[mid]` Tesseract'ta sınırda güvenle okunur (karenin anına göre ~55–75): okunursa
    # doğru okunur, okunamazsa metne girmez. Okunan her kelime slaytta vardır (uydurma yok;
    # ok uçları gibi harfsiz işaretler hariç).
    assert code.status == "readable"
    assert "while lo <= hi:" in code.text and "== x: return mid" in code.text
    for frame, (_, _, slide) in zip((formula, code, diagram), LECTURE, strict=False):
        on_slide = " ".join([slide.title, *slide.lines, *slide.diagram]).split()
        read = {word for word in frame.text.split() if any(c.isalnum() for c in word)}
        assert read <= set(on_slide), frame.text
    assert diagram.status == "readable"
    assert all(label in diagram.text for label in ("Dijkstra", "Kaynak", "Kuyruk", "Hedef"))
    assert (blank.status, blank.text, blank.embedding) == ("no_text", None, None)
    for frame in (formula, code, diagram):
        assert frame.confidence is not None and frame.confidence >= 0.8
        assert frame.embedding is not None

    # Orijinal kare: gerçek PNG, dersin üyesine sunulur.
    image = client.get(f"/documents/{document.id}/frames/{diagram.id}.png")
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")

    # Transkriptte olmayan diyagram etiketi kare aramasında bulunur, bağlamıyla.
    transcript = " ".join(db.scalars(select(Chunk.text).where(Chunk.document_id == document.id)))
    assert "kaynak" not in transcript.lower()
    best = frame_search(db, course, "Dijkstra kaynak dugum", FakeEmbedder())[0]
    assert best.frame.id == diagram.id
    # Kısa konuşma tek parçada birleşir (0,5–17,5 sn; parça tavanı 60 sn): bağlam o parçadır.
    (chunk,) = db.scalars(select(Chunk).where(Chunk.document_id == document.id)).all()
    assert (chunk.t_start, chunk.t_end) == (0.5, 17.5)
    assert [c.id for c in best.transcript] == [chunk.id] and SPEECH[2].text in chunk.text
    assert [frame.id for frame in best.neighbors] == [code.id, blank.id]

    # Kaynak görüntüleyici: konuşma parçasının aralığında ekranda olan üç slayt, zamana göre.
    source = client.get(f"/sources/{chunk.id}").json()
    assert [frame["frame_id"] for frame in source["frames"]] == [formula.id, code.id, diagram.id]
    assert source["frames"][2]["image_url"].endswith(f"/frames/{diagram.id}.png")


def test_white_labels_in_dark_filled_boxes_are_read(tmp_path: Path) -> None:
    """PowerPoint'in varsayılan şekli: koyu dolu kutu, beyaz yazı (gerçek derste kaçırılmıştı)."""
    slides = [Slide(4, "Dijkstra", diagram=("Kaynak", "Kuyruk", "Hedef"), filled=True)]
    video = make_lecture_video(tmp_path / "kutular.mp4", slides)

    (frame,) = extract_frames(video, tmp_path / "frames")
    result = read_image(frame.image_path, "tur+eng")

    assert result.status == "readable"
    assert all(label in result.text for label in ("Dijkstra", "Kaynak", "Kuyruk", "Hedef"))


def test_large_title_letters_are_not_erased_as_lines(tmp_path: Path) -> None:
    """Büyük başlıkta harf gövdeleri (G, h, İ) çizgi sanılıp silinmemeli (gerçek derste
    "Graph Search" → "Grad Searcr", "İkili" → "ili" olmuştu)."""
    slides = [Slide(4, "Graph Search", ["Algorithms - Lecture 3"], title_size=110)]
    video = make_lecture_video(tmp_path / "baslik.mp4", slides)

    (frame,) = extract_frames(video, tmp_path / "frames")
    result = read_image(frame.image_path, "eng")

    assert result.status == "readable"
    assert "Graph Search" in result.text and "Lecture 3" in result.text


def test_audio_only_media_has_no_frames(
    client: TestClient, db: Session, course: Course, process, tmp_path: Path
) -> None:
    audio = tmp_path / "ders.wav"
    with wave.open(str(audio), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(struct.pack("<h", 0) * 16000)

    document = process(client, course, "ders.wav", audio.read_bytes())

    assert document.status == "ready" and frames_of(db, document) == []


def test_undecodable_video_keeps_the_transcript_without_frames(
    client: TestClient, db: Session, course: Course, process
) -> None:
    broken = b"\x00\x00\x00\x18ftypmp42" + b"\x13\x37" * 4096

    document = process(client, course, "bozuk.mp4", broken)

    assert (document.status, document.error) == ("ready", None)
    assert frames_of(db, document) == []
    assert not (settings.upload_dir / str(course.id) / "frames" / str(document.id)).exists()
