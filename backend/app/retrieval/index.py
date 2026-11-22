"""İndeksin kimliği: hangi parçalar, hangi embedder'la vektörleştirildi.

Değerlendirme koşuları ve `reembed` betiği bunu kaydeder/gösterir; anlamsal arama
yalnızca etkin embedder'ın kimliğiyle eşleşen vektörleri kullanır (bkz. `dense.py`).
"""

import hashlib
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Course, VideoFrame


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


@dataclass
class FrameInventory:
    """Kare (görsel çıkarım) indeksinin kimliği (#29).

    Parmak izi karelerin zamanından, durumundan, OCR metninden, çıkarıcı kimliğinden
    (`extractor`: araç, dil, örnekleme), embedder kimliğinden ve yorumlayıcı kimliği + yorum
    metninden oluşur. Kare/doküman kimliklerinden ve görüntü yolundan bağımsızdır: aynı video
    aynı ayarlarla yeniden çıkarılırsa değişmez; çıkarıcı ya da model değişince değişir.
    """

    frames: int
    by_status: dict[str, int]
    extractors: list[str]
    by_embedding: dict[str | None, int]
    interpreters: list[str]
    fingerprint: str


def frame_inventory(db: Session, course_id: int | None = None) -> FrameInventory:
    query = select(
        VideoFrame.t_start,
        VideoFrame.t_end,
        VideoFrame.status,
        VideoFrame.text,
        VideoFrame.extractor,
        VideoFrame.embedding_model,
        VideoFrame.embedding.is_not(None),
        VideoFrame.description,
        VideoFrame.description_model,
    )
    if course_id is not None:
        query = query.where(VideoFrame.course_id == course_id)
    by_status: dict[str, int] = {}
    by_embedding: dict[str | None, int] = {}
    extractors: set[str] = set()
    interpreters: set[str] = set()
    entries: list[str] = []
    for (
        t_start,
        t_end,
        status,
        text,
        extractor,
        model,
        has_vector,
        description,
        described_by,
    ) in db.execute(query):
        by_status[status] = by_status.get(status, 0) + 1
        vector_of = model if has_vector else None
        by_embedding[vector_of] = by_embedding.get(vector_of, 0) + 1
        extractors.add(extractor)
        if described_by:
            interpreters.add(described_by)
        entries.append(
            "|".join(
                (
                    f"{t_start:.3f}",
                    f"{t_end:.3f}",
                    status,
                    _hash(text),
                    extractor,
                    vector_of or "-",
                    described_by or "-",
                    _hash(description),
                )
            )
        )
    digest = hashlib.sha256("\n".join(sorted(entries)).encode("utf-8")).hexdigest()
    return FrameInventory(
        frames=len(entries),
        by_status=by_status,
        extractors=sorted(extractors),
        by_embedding=by_embedding,
        interpreters=sorted(interpreters),
        fingerprint=digest,
    )


def _hash(text: str | None) -> str:
    return "-" if text is None else hashlib.sha256(text.encode("utf-8")).hexdigest()


def stale_chunk_count(db: Session, identity: str, course_id: int | None = None) -> int:
    query = select(func.count(Chunk.id)).where(
        Chunk.embedding.is_(None) | Chunk.embedding_model.is_distinct_from(identity)
    )
    if course_id is not None:
        query = query.where(Chunk.course_id == course_id)
    return db.scalar(query) or 0
