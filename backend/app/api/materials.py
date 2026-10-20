from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.deps import DbSession, get_course_or_404
from app.db.models import Document
from app.ingestion.documents import chunk_previews, list_documents, to_document_out
from app.ingestion.pipeline import IngestionError, ingest_document
from app.ingestion.rendering import page_image_path, remove_cached_pages
from app.schemas.materials import ChunkPreview, DocumentOut, MaterialType

router = APIRouter(tags=["materials"])

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".vtt": "text/vtt",
}


@router.post(
    "/courses/{course_id}/materials",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
def upload_material(
    course_id: int,
    db: DbSession,
    material_type: Annotated[MaterialType, Form()],
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    media_url: Annotated[str | None, Form()] = None,
) -> DocumentOut:
    """FR-01..02: onaylı materyali yükle → parse → temizle → parçala → vektörleştir.

    `.vtt` altyazısı video olarak kaydedilir; `media_url` (https) videonun harici oynatma
    adresidir. Cevaptaki `report`, hattın her adımında ne olduğunu gösterir.
    """
    course = get_course_or_404(db, course_id)
    try:
        document, report = ingest_document(
            db,
            course,
            filename=file.filename or "dosya",
            content=file.file.read(),
            material_type=material_type,
            title=title,
            media_url=media_url,
        )
    except IngestionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    result = to_document_out(document, len(document.chunks))
    result.report = report
    return result


@router.get("/courses/{course_id}/materials", response_model=list[DocumentOut])
def list_materials(course_id: int, db: DbSession) -> list[DocumentOut]:
    """Dersin yüklenmiş dokümanları ve parça sayıları."""
    get_course_or_404(db, course_id)
    return list_documents(db, course_id)


@router.get("/documents/{document_id}/chunks", response_model=list[ChunkPreview])
def document_chunks(document_id: int, db: DbSession) -> list[ChunkPreview]:
    """Sistemin dokümandan çıkardığı parçalar (sayfa numaralarıyla)."""
    return chunk_previews(_get_document_or_404(db, document_id))


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: DbSession) -> None:
    """Dokümanı, parçalarını, dosyasını ve sayfa görüntülerini siler."""
    document = _get_document_or_404(db, document_id)
    path = Path(document.file_path) if document.file_path else None
    db.delete(document)
    db.commit()
    if path:
        path.unlink(missing_ok=True)
    remove_cached_pages(document_id)


@router.get("/documents/{document_id}/pages/{page}.png")
def document_page_image(document_id: int, page: int, db: DbSession) -> FileResponse:
    """PDF sayfasının görüntüsü (kaynak görüntüleyici için)."""
    image = page_image_path(_get_document_or_404(db, document_id), page)
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sayfa görüntüsü yok")
    return FileResponse(image, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@router.get("/documents/{document_id}/file")
def document_file(document_id: int, db: DbSession) -> FileResponse:
    """Orijinal dosya. PDF tarayıcıda `#page=N` ile ilgili sayfada açılır."""
    document = _get_document_or_404(db, document_id)
    path = Path(document.file_path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dosya bulunamadı")
    return FileResponse(
        path,
        media_type=_MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        filename=document.filename,
        content_disposition_type="inline",
    )


def _get_document_or_404(db: DbSession, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Doküman bulunamadı")
    return document
