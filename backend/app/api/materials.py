from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from app.api.not_implemented import not_implemented
from app.schemas.materials import MaterialType, MaterialUploadResponse

router = APIRouter(prefix="/courses/{course_id}/materials", tags=["materials"])


@router.post("", response_model=MaterialUploadResponse)
def upload_material(
    course_id: int,
    material_type: Annotated[MaterialType, Form()],
    file: Annotated[UploadFile, File()],
) -> MaterialUploadResponse:
    """FR-01..03: onaylı materyali yükle → ingestion pipeline (eğitmen yetkisi)."""
    not_implemented("Materyal yükleme / ingestion")
