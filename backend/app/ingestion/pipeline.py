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
from app.ingestion.chunking import chunk_segments, chunk_timed_segments
from app.ingestion.cleaning import clean_segments_with_stats, normalize_timed_segments
from app.ingestion.documents import validate_media_url
from app.ingestion.parsers.pdf_parser import parse_pdf
from app.ingestion.parsers.pptx_parser import parse_pptx
from app.ingestion.parsers.vtt_parser import ParsedVtt, parse_vtt
from app.ingestion.types import ChunkDraft, IngestionError, RawSegment
from app.schemas.materials import IngestionReport, MaterialType

PARSERS: dict[str, Callable[[Path], list[RawSegment]]] = {
    ".pdf": parse_pdf,
    ".pptx": parse_pptx,
}
VTT_EXTENSION = ".vtt"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def supported_extensions() -> list[str]:
    return sorted([*PARSERS, VTT_EXTENSION])


def ingest_document(
    db: Session,
    course: Course,
    filename: str,
    content: bytes,
    material_type: MaterialType,
    title: str | None = None,
    embedder: Embedder | None = None,
    media_url: str | None = None,
    approved_by: int | None = None,
) -> tuple[Document, IngestionReport]:
    """Dosyayı kaydet → parse → temizle → parçala → vektörleştir → Document + Chunk yaz.

    Yükleme onay sayılır (ADR-3): yalnızca eğitmen yükler ve beyanı işaretler; `approved_by`
    yükleyen eğitmendir.

    `.vtt` altyazısı her zaman `video` türünde kaydedilir; parçalar sayfa yerine zaman
    aralığı taşır. `media_url`, videonun harici (opak, https) oynatma adresidir.

    Hata olursa veritabanı değişiklikleri geri alınır ve kaydedilen dosya silinir.
    """
    extension = Path(filename).suffix.lower()
    if material_type == MaterialType.VIDEO and extension != VTT_EXTENSION:
        raise IngestionError(
            "Video türünde yalnızca altyazı (.vtt) ya da ders videosu/sesi yüklenir."
        )
    if extension != VTT_EXTENSION and extension not in PARSERS:
        raise IngestionError(
            f"Desteklenmeyen dosya türü: {extension or '(uzantısız)'}. "
            f"Desteklenenler: {', '.join(supported_extensions())}"
        )
    is_video = extension == VTT_EXTENSION
    if media_url is not None:
        if not is_video:
            raise IngestionError("Medya adresi yalnızca video (.vtt) yüklemesinde verilebilir.")
        validate_media_url(media_url)
    if not content:
        raise IngestionError("Dosya boş.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise IngestionError("Dosya 50 MB sınırını aşıyor.")
    embedder = embedder or get_embedder()

    document = Document(
        course_id=course.id,
        title=title or Path(filename).stem,
        material_type=MaterialType.VIDEO.value if is_video else material_type.value,
        filename=Path(filename).name,
        file_path="",
        media_url=media_url,
        approved_by=approved_by,
        approved_at=func.now(),
        transcript_source="vtt" if is_video else None,
    )
    db.add(document)
    db.flush()

    path = settings.upload_dir / str(course.id) / f"{document.id}{extension}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    timings: dict[str, int] = {}
    parsed: ParsedVtt | None = None
    try:
        with _timed(timings, "parse"):
            try:
                if is_video:
                    parsed = parse_vtt(path)
                    segments = parsed.segments
                else:
                    segments = PARSERS[extension](path)
            except IngestionError:
                raise
            except Exception as exc:
                raise IngestionError("Dosya okunamadı; bozuk ya da şifreli olabilir.") from exc

        drafts: list[ChunkDraft]
        with _timed(timings, "clean"):
            if is_video:
                cleaned, stats = normalize_timed_segments(segments)
            else:
                cleaned, stats = clean_segments_with_stats(segments)
        with _timed(timings, "chunk"):
            drafts = chunk_timed_segments(cleaned) if is_video else chunk_segments(cleaned)
        if not drafts:
            raise IngestionError(
                "Altyazıdan metin çıkarılamadı."
                if is_video
                else "Dosyadan metin çıkarılamadı. Taranmış (görüntü) bir PDF olabilir."
            )

        with _timed(timings, "embed"):
            vectors = embedder.embed_passages([draft.text for draft in drafts])

        document.file_path = str(path)
        document.page_count = 0 if is_video else len(segments)
        if parsed is not None:
            document.duration_s = parsed.duration_s
        add_chunks(db, course, document, drafts, vectors, embedder)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    db.refresh(document)

    report = IngestionReport(
        pages_read=0 if is_video else len(segments),
        empty_pages=0 if is_video else stats.empty_segments_dropped,
        repeated_lines_removed=stats.repeated_lines_removed,
        page_numbers_removed=stats.page_numbers_removed,
        chunks=len(drafts),
        vectors=len(vectors),
        vector_dim=embedder.dim,
        embedding_model=settings.embedding_model if embedder.name == "e5" else embedder.name,
        timings_ms=timings,
        **_video_report_fields(parsed),
    )
    return document, report


def add_chunks(
    db: Session,
    course: Course,
    document: Document,
    drafts: list[ChunkDraft],
    vectors: list[list[float]],
    embedder: Embedder,
) -> None:
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
            embedding_model=embedder.identity,
        )
        for ordinal, (draft, vector) in enumerate(zip(drafts, vectors, strict=True))
    )


def _video_report_fields(parsed: ParsedVtt | None) -> dict[str, object]:
    if parsed is None:
        return {}
    warnings = []
    if parsed.cues_skipped:
        warnings.append(
            f"{parsed.cues_skipped} altyazı satırı okunamadı ve atlandı; "
            "o aralıklar aramada bulunmayacak."
        )
    return {
        "duration_s": parsed.duration_s,
        "cues_read": parsed.cues_read,
        "cues_skipped": parsed.cues_skipped,
        "warnings": warnings,
    }


class _timed:
    """Bir adımın süresini milisaniye olarak `timings[name]`e yazar."""

    def __init__(self, timings: dict[str, int], name: str) -> None:
        self.timings = timings
        self.name = name

    def __enter__(self) -> None:
        self.start = time.perf_counter()

    def __exit__(self, *_: object) -> None:
        self.timings[self.name] = round((time.perf_counter() - self.start) * 1000)
