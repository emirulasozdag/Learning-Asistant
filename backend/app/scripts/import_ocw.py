"""MIT OpenCourseWare "Download Course" paketini bir ders olarak içeri alır.

Kullanım: python -m app.scripts.import_ocw /code/data/ocw/6-006-spring-2020

Ders yoksa oluşturur, varsa bilgisini, izlencesini ve takvimini günceller. PDF'leri normal
yükleme hattından geçirir (parse → temizle → parçala → vektörleştir). Tekrar çalıştırılabilir:
aynı başlıkta dokümanı olan dosyalar atlanır.
"""

import argparse
import time
from pathlib import Path

from sqlalchemy import select

from app.db.models import Course, Document
from app.db.session import SessionLocal
from app.embeddings.provider import get_embedder
from app.ingestion import ocw
from app.ingestion.pipeline import IngestionError, ingest_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", type=Path, help="OCW paketinin klasörü (içinde data.json)")
    root: Path = parser.parse_args().package
    if not (root / "data.json").is_file():
        raise SystemExit(f"OCW paketi bulunamadı: {root}/data.json yok")

    info = ocw.read_course(root)
    files = ocw.list_files(root)
    embedder = get_embedder()

    with SessionLocal() as db:
        course = db.scalar(select(Course).where(Course.code == info.code))
        if course is None:
            course = Course(code=info.code, name=info.name, language="en")
            db.add(course)
            print(f"Ders oluşturuldu: {info.code} — {info.name}")
        else:
            print(f"Ders güncelleniyor: {info.code} (id={course.id})")
        course.name = info.name
        course.instructor_name = info.instructor_name
        course.term = info.term
        course.level = info.level
        course.department = info.department
        course.description = info.description
        course.syllabus = ocw.read_syllabus(root)
        course.calendar = ocw.read_calendar(root)
        db.commit()

        existing = set(db.scalars(select(Document.title).where(Document.course_id == course.id)))
        added = skipped = failed = pages = chunks = 0
        started = time.monotonic()
        for index, item in enumerate(files, start=1):
            prefix = f"[{index}/{len(files)}] {item.material_type.value:<16} {item.title}"
            if item.title in existing:
                skipped += 1
                print(f"{prefix} — zaten var, atlandı")
                continue
            try:
                _, report = ingest_document(
                    db,
                    course,
                    filename=item.filename,
                    content=item.path.read_bytes(),
                    material_type=item.material_type,
                    title=item.title,
                    embedder=embedder,
                )
            except IngestionError as exc:
                failed += 1
                print(f"{prefix} — HATA: {exc}")
                continue
            added += 1
            pages += report.pages_read
            chunks += report.chunks
            print(f"{prefix} — {report.pages_read} sayfa, {report.chunks} parça")

        elapsed = time.monotonic() - started
        print(
            f"\nBitti ({course.code}, id={course.id}): {added} eklendi, {skipped} atlandı, "
            f"{failed} hata. Yeni: {pages} sayfa, {chunks} parça, {elapsed:.0f} sn."
        )
        print(
            f"İzlence: {len(course.syllabus or [])} blok, "
            f"takvim: {len((course.calendar or {}).get('rows', []))} hafta."
        )


if __name__ == "__main__":
    main()
