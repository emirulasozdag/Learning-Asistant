import time
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import cast, func, literal
from sqlalchemy.dialects.postgresql import REGCONFIG
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Chunk, Course, Document
from app.db.text_search import ts_config
from app.embeddings.base import Embedder
from app.embeddings.provider import get_embedder
from app.ingestion.chunking import chunk_segments
from app.ingestion.cleaning import clean_segments_with_stats
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.pptx_parser import parse_pptx
from app.ingestion.types import RawSegment
from app.schemas.materials import IngestionReport, MaterialType

PARSERS: dict[str, Callable[[Path], list[RawSegment]]] = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


class IngestionError(ValueError):
    """Kullanıcıya gösterilecek, düzeltilebilir bir yükleme hatası."""


def supported_extensions() -> list[str]:
    return sorted(PARSERS)


def ingest_document(
    db: Session,
    course: Course,
    filename: str,
    content: bytes,
    material_type: MaterialType,
    title: str | None = None,
    embedder: Embedder | None = None,
) -> tuple[Document, IngestionReport]:
    """Dosyayı kaydet → parse → temizle → parçala → vektörleştir → Document + Chunk yaz.

    Hata olursa veritabanı değişiklikleri geri alınır ve kaydedilen dosya silinir.
    """
    extension = Path(filename).suffix.lower()
    if extension not in PARSERS:
        raise IngestionError(
            f"Desteklenmeyen dosya türü: {extension or '(uzantısız)'}. "
            f"Desteklenenler: {', '.join(supported_extensions())}"
        )
    if not content:
        raise IngestionError("Dosya boş.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise IngestionError("Dosya 50 MB sınırını aşıyor.")
    embedder = embedder or get_embedder()

    document = Document(
        course_id=course.id,
        title=title or Path(filename).stem,
        material_type=material_type.value,
        filename=Path(filename).name,
        file_path="",
    )
    db.add(document)
    db.flush()

    path = settings.upload_dir / str(course.id) / f"{document.id}{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    timings: dict[str, int] = {}
    try:
        with _timed(timings, "parse"):
            try:
                segments = PARSERS[extension](path)
            except Exception as exc:
                raise IngestionError("Dosya okunamadı; bozuk ya da şifreli olabilir.") from exc

        with _timed(timings, "clean"):
            cleaned, stats = clean_segments_with_stats(segments)
        with _timed(timings, "chunk"):
            drafts = chunk_segments(cleaned)
        if not drafts:
            raise IngestionError(
                "Dosyadan metin çıkarılamadı. Taranmış (görüntü) bir PDF olabilir."
            )

        with _timed(timings, "embed"):
            vectors = embedder.embed_passages([draft.text for draft in drafts])

        document.file_path = str(path)
        document.page_count = len(segments)
        config = cast(literal(ts_config(course.language)), REGCONFIG)
        db.add_all(
            Chunk(
                document_id=document.id,
                course_id=course.id,
                ordinal=ordinal,
                text=draft.text,
                page=draft.page,
                t_start=draft.t_start,
                t_end=draft.t_end,
                search_vector=func.to_tsvector(config, draft.text),
                embedding=vector,
            )
            for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
        )
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(document)

    report = IngestionReport(
        pages_read=len(segments),
        empty_pages=stats.empty_segments_dropped,
        repeated_lines_removed=stats.repeated_lines_removed,
        page_numbers_removed=stats.page_numbers_removed,
        chunks=len(drafts),
        vectors=len(vectors),
        vector_dim=embedder.dim,
        embedding_model=settings.embedding_model if embedder.name == "e5" else embedder.name,
        timings_ms=timings,
    )
    return document, report


class _timed:
    """Bir adımın süresini milisaniye olarak `timings[name]`e yazar."""

    def __init__(self, timings: dict[str, int], name: str) -> None:
        self.timings = timings
        self.name = name

    def __enter__(self) -> None:
        self.start = time.perf_counter()

    def __exit__(self, *_: object) -> None:
        self.timings[self.name] = round((time.perf_counter() - self.start) * 1000)
