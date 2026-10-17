from pathlib import Path

from app.schemas.materials import MaterialType


def ingest_document(course_id: int, path: Path, material_type: MaterialType) -> int:
    """parse → clean → chunk → embed → kaydet. Oluşan parça sayısını döndürür."""
    raise NotImplementedError
