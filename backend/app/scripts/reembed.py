"""Parça vektörlerini etkin embedder'la yeniden üretir (bilinçli yeniden oluşturma yolu).

Kullanım:
    python -m app.scripts.reembed [--course KOD] [--all] [--dry-run]

Varsayılan: vektörü olmayan ya da başka bir embedder'la (ör. testlerin sahte embedder'ı,
eski bir model) üretilmiş parçalar. `--all` hepsini yeniden üretir. `--dry-run` yalnızca
indeksin durumunu gösterir. Embedding modeli (EMBEDDING_MODEL) değiştiğinde çalıştırın;
o zamana kadar anlamsal arama eski vektörleri kullanmaz, kelime araması çalışmaya devam eder.
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course
from app.db.session import SessionLocal
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.retrieval.index import inventory

BATCH = 64


def reembed(
    db: Session, embedder: Embedder, course_id: int | None = None, all_chunks: bool = False
) -> int:
    """Uyumsuz (ya da `all_chunks` ile tüm) parçaları yeniden vektörleştirir; sayıyı döner.

    Her parti kendi işleminde yazılır: yarıda kesilirse kalan parçalar bir sonraki çalıştırmada
    devam eder; arada arama yalnızca yeni kimlikli vektörleri kullanır, ikisi karışmaz.
    """
    query = select(Chunk).order_by(Chunk.id)
    if course_id is not None:
        query = query.where(Chunk.course_id == course_id)
    if not all_chunks:
        query = query.where(
            Chunk.embedding.is_(None) | Chunk.embedding_model.is_distinct_from(embedder.identity)
        )
    chunks = list(db.scalars(query))
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start : start + BATCH]
        vectors = embedder.embed_passages([c.text for c in batch])
        for chunk, vector in zip(batch, vectors, strict=True):
            chunk.embedding = vector
            chunk.embedding_model = embedder.identity
        db.commit()
    return len(chunks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.scripts.reembed")
    parser.add_argument("--course", help="Yalnızca bu ders kodu")
    parser.add_argument("--all", action="store_true", help="Uyumlu vektörleri de yeniden üret")
    parser.add_argument("--dry-run", action="store_true", help="Yalnızca durumu göster")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    embedder = get_embedder()
    with SessionLocal() as db:
        course_id = None
        if args.course:
            course = db.scalar(select(Course).where(Course.code == args.course.upper()))
            if course is None:
                print(f"{args.course} kodlu ders yok.")
                return 1
            course_id = course.id
        before = inventory(db, course_id)
        print(f"Etkin embedder: {embedder.identity}")
        print(f"Parça: {before.chunks}, vektörsüz: {before.without_vector}")
        for identity, count in sorted(before.by_embedding.items(), key=lambda kv: str(kv[0])):
            print(f"  {identity or '(kimliksiz)'}: {count}")
        if args.dry_run:
            print(f"Yeniden üretilecek: {before.stale(embedder.identity)} (--all ile hepsi)")
            return 0
        count = reembed(db, embedder, course_id, all_chunks=args.all)
        print(f"{count} parça vektörleştirildi ({embedder.identity}).")
        print(f"İndeks parmak izi: {inventory(db, course_id).fingerprint[:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
