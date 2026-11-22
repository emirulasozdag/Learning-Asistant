"""MIT OpenCourseWare "Download Course" paketini bir ders olarak içeri alır.

Kullanım: python -m app.scripts.import_ocw /code/data/ocw/6-006-spring-2020 [--frames N]

Ders yoksa oluşturur, varsa bilgisini, izlencesini ve takvimini günceller. PDF'leri ve ders
videolarını (paketteki altyazı + YouTube adresi) normal yükleme hattından geçirir (parse → temizle
→ parçala → vektörleştir). Tekrar çalıştırılabilir: aynı türde ve başlıkta dokümanı olan dosyalar
atlanır (ders notu ile videosu aynı başlığı taşıyabilir).
Derse özel kod yoktur: ikinci ders de aynı paket yapısıyla eklenir (#28).

`--frames N`: kare çıkarma açıksa (FRAME_EXTRACTION=ocr) ilk N videonun mp4'ü OCW'nin verdiği
adresten indirilir ve slayt kareleri için kuyruğa alınır (#27); kareler `worker` bitirince görünür.
Videonun kendisi saklanmaz. Varsayılan 0: hiçbir şey indirilmez.

Betikle açılan dersin üyesi yoktur; dersi görebilmek için bir eğitmene bağlayın:
    python -m app.scripts.create_instructor --email ... --name "..." --course 6.006
"""

import argparse
import time
import urllib.request
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.demo import enroll_dev_instructor
from app.core.config import settings
from app.db.models import Course, Document, VideoFrame
from app.db.session import SessionLocal
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.ingestion import ocw
from app.ingestion.media import add_frame_media
from app.ingestion.pipeline import IngestionError, ingest_document
from app.jobs.queue import active_job
from app.schemas.materials import MaterialType

# mp4'ü indiren fonksiyon: adres → okunabilir akış (testlerde sahtesi verilir).
Fetch = Callable[[str], AbstractContextManager[BinaryIO]]
DOWNLOAD_TIMEOUT_S = 60


@dataclass
class ImportSummary:
    course: Course
    added: int = 0
    skipped: int = 0
    failed: int = 0
    pages: int = 0
    chunks: int = 0
    videos: int = 0
    frames_queued: int = 0
    without_captions: list[str] = field(default_factory=list)


def download(url: str) -> AbstractContextManager[BinaryIO]:
    """OCW'nin verdiği https adresinden akış (belleğe okunmaz; `add_frame_media` diske kopyalar)."""
    if not url.startswith("https://"):
        raise IngestionError(f"Güvenli olmayan adres: {url}")
    return urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S)  # noqa: S310 (yalnızca https)


def import_package(
    db: Session,
    root: Path,
    embedder: Embedder,
    *,
    language: str = "en",
    frames: int = 0,
    fetch: Fetch = download,
    log: Callable[[str], None] = print,
) -> ImportSummary:
    """Paketi içeri alır; özet döner. Hata veren dosya atlanır, diğerleri devam eder."""
    info = ocw.read_course(root)
    course = db.scalar(select(Course).where(Course.code == info.code))
    if course is None:
        course = Course(code=info.code, name=info.name, language=language)
        db.add(course)
        log(f"Ders oluşturuldu: {info.code} — {info.name}")
    else:
        log(f"Ders güncelleniyor: {info.code} (id={course.id})")
    course.name = info.name
    course.instructor_name = info.instructor_name
    course.term = info.term
    course.level = info.level
    course.department = info.department
    course.description = info.description
    course.syllabus = ocw.read_syllabus(root)
    course.calendar = ocw.read_calendar(root)
    db.commit()
    if enroll_dev_instructor(db, course):
        log(f"Demo eğitmeni ({settings.dev_instructor_email}) dersin eğitmeni yapıldı.")

    summary = ImportSummary(course=course)
    # Ders notu ile videosu çoğu zaman aynı başlığı taşır ("Lecture 6: Binary Trees, Part 1"):
    # tekrarı başlık ve tür birlikte belirler.
    existing = {
        (MaterialType(material_type), title)
        for material_type, title in db.execute(
            select(Document.material_type, Document.title).where(Document.course_id == course.id)
        )
    }
    files = ocw.list_files(root)
    videos, summary.without_captions = ocw.list_videos(root, course.language)
    items: list[tuple[str, str, Path, MaterialType, str | None]] = [
        (f.title, f.filename, f.path, f.material_type, None) for f in files
    ] + [(v.title, v.filename, v.captions, MaterialType.VIDEO, v.media_url) for v in videos]
    for index, (title, filename, path, material_type, media_url) in enumerate(items, start=1):
        prefix = f"[{index}/{len(items)}] {material_type.value:<16} {title}"
        if (material_type, title) in existing:
            summary.skipped += 1
            log(f"{prefix} — zaten var, atlandı")
            continue
        try:
            _, report = ingest_document(
                db,
                course,
                filename=filename,
                content=path.read_bytes(),
                material_type=material_type,
                title=title,
                embedder=embedder,
                media_url=media_url,
            )
        except IngestionError as exc:
            summary.failed += 1
            log(f"{prefix} — HATA: {exc}")
            continue
        existing.add((material_type, title))
        summary.added += 1
        summary.pages += report.pages_read
        summary.chunks += report.chunks
        if material_type == MaterialType.VIDEO:
            summary.videos += 1
        log(f"{prefix} — {report.pages_read} sayfa, {report.chunks} parça")
    for title in summary.without_captions:
        log(f"Video atlandı (pakette altyazısı yok): {title}")

    if frames > 0:
        summary.frames_queued = _queue_frames(db, course, videos[:frames], fetch, log)
    return summary


def _queue_frames(
    db: Session,
    course: Course,
    videos: list[ocw.OcwVideo],
    fetch: Fetch,
    log: Callable[[str], None],
) -> int:
    """Karesi olmayan ilk videoların mp4'ünü indirip kare işini kuyruğa alır (#27)."""
    queued = 0
    for video in videos:
        document = db.scalar(
            select(Document).where(
                Document.course_id == course.id,
                Document.material_type == MaterialType.VIDEO.value,
                Document.title == video.title,
            )
        )
        if document is None or document.status != "ready" or not video.archive_url:
            continue
        has_frames = db.scalar(
            select(func.count(VideoFrame.id)).where(VideoFrame.document_id == document.id)
        )
        if has_frames or active_job(db, document.id) is not None:
            log(f"Kareler zaten var ya da hazırlanıyor: {video.title}")
            continue
        try:
            with fetch(video.archive_url) as stream:
                add_frame_media(db, document, Path(video.archive_url).name, stream)
        except (IngestionError, OSError) as exc:
            db.rollback()
            log(f"Kareler kuyruğa alınamadı ({video.title}): {exc}")
            continue
        queued += 1
        log(f"Kareler kuyrukta: {video.title}")
    return queued


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", type=Path, help="OCW paketinin klasörü (içinde data.json)")
    parser.add_argument("--language", choices=["en", "tr"], default="en", help="Yeni dersin dili")
    parser.add_argument(
        "--frames", type=int, default=0, help="Kareleri çıkarılacak video sayısı (mp4 indirilir)"
    )
    args = parser.parse_args()
    root: Path = args.package
    if not (root / "data.json").is_file():
        raise SystemExit(f"OCW paketi bulunamadı: {root}/data.json yok")

    started = time.monotonic()
    with SessionLocal() as db:
        summary = import_package(
            db, root, get_embedder(), language=args.language, frames=args.frames
        )
        course = summary.course
        print(
            f"\nBitti ({course.code}, id={course.id}): {summary.added} eklendi "
            f"({summary.videos} video), {summary.skipped} atlandı, {summary.failed} hata. "
            f"Yeni: {summary.pages} sayfa, {summary.chunks} parça, "
            f"{time.monotonic() - started:.0f} sn."
        )
        print(
            f"İzlence: {len(course.syllabus or [])} blok, "
            f"takvim: {len((course.calendar or {}).get('rows', []))} hafta."
        )
        if summary.frames_queued:
            print(f"{summary.frames_queued} videonun kareleri kuyrukta; worker bitirince görünür.")
        if not settings.seed_dev_accounts:
            print(
                "Dersi görmek için bir eğitmene bağlayın: python -m app.scripts.create_instructor "
                f'--email ... --name "..." --course {course.code}'
            )


if __name__ == "__main__":
    main()
