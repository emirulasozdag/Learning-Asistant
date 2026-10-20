"""İndeksin kimliği: hangi parçalar, hangi embedder'la vektörleştirildi.

Değerlendirme koşuları ve `reembed` betiği bunu kaydeder/gösterir; anlamsal arama
yalnızca etkin embedder'ın kimliğiyle eşleşen vektörleri kullanır (bkz. `dense.py`).
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course


@dataclass
class IndexInventory:
    chunks: int
    # Embedder kimliği → vektörlü parça sayısı (None: kimliği bilinmeyen eski vektör).
    by_embedding: dict[str | None, int]
    without_vector: int
    # Parça metinleri + konumları + embedder kimlikleri + FTS dili; aynı materyal aynı parçalama
    # ve aynı embedder'la yeniden indekslenirse değişmez (chunk/doküman id'lerinden bağımsız).
    # Vektör değerleri girmez: aynı model farklı makinede küçük sayısal farklar üretebilir;
    # model ağırlıklarının değişmesi kimlikte (sürüm) yakalanmalıdır.
    fingerprint: str

    def stale(self, identity: str) -> int:
        """Etkin embedder'la arama yapılamayan (vektörsüz ya da başka kimlikli) parça sayısı."""
        return self.chunks - self.by_embedding.get(identity, 0)


def inventory(db: Session, course_id: int | None = None) -> IndexInventory:
    query = select(
        Chunk.page,
        Chunk.t_start,
        Chunk.t_end,
        Chunk.text,
        Chunk.embedding_model,
        Chunk.embedding,
        Course.language,
    ).join(Course, Course.id == Chunk.course_id)
    if course_id is not None:
        query = query.where(Chunk.course_id == course_id)
    by_embedding: dict[str | None, int] = {}
    without_vector = 0
    entries: list[str] = []
    chunks = 0
    for page, t_start, t_end, text, model, embedding, language in db.execute(query):
        chunks += 1
        if embedding is None:
            without_vector += 1
        else:
            by_embedding[model] = by_embedding.get(model, 0) + 1
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        vector_of = model if embedding is not None else "-"
        entries.append(f"{language}|{page}|{t_start}|{t_end}|{text_hash}|{vector_of}")
    digest = hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()
    return IndexInventory(chunks, by_embedding, without_vector, digest)


def stale_chunk_count(db: Session, identity: str, course_id: int | None = None) -> int:
    query = select(func.count(Chunk.id)).where(
        Chunk.embedding.is_(None) | Chunk.embedding_model.is_distinct_from(identity)
    )
    if course_id is not None:
        query = query.where(Chunk.course_id == course_id)
    return db.scalar(query) or 0
