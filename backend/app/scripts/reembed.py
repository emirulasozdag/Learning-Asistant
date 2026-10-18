"""Vektörü olmayan (ya da tümü) parçaları yeniden vektörleştirir.

Kullanım: python -m app.scripts.reembed [--all]
Embedding modeli değiştiğinde --all ile çalıştırın.
"""

import sys

from sqlalchemy import select

from app.db.models import Chunk
from app.db.session import SessionLocal
from app.embeddings.provider import get_embedder

BATCH = 64


def main(all_chunks: bool = False) -> None:
    embedder = get_embedder()
    with SessionLocal() as db:
        query = select(Chunk).order_by(Chunk.id)
        if not all_chunks:
            query = query.where(Chunk.embedding.is_(None))
        chunks = list(db.scalars(query))
        for start in range(0, len(chunks), BATCH):
            batch = chunks[start : start + BATCH]
            for chunk, vector in zip(
                batch, embedder.embed_passages([c.text for c in batch]), strict=True
            ):
                chunk.embedding = vector
            db.commit()
        print(f"{len(chunks)} parça vektörleştirildi ({embedder.name}).")


if __name__ == "__main__":
    main(all_chunks="--all" in sys.argv)
