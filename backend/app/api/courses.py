from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession
from app.courses import service
from app.schemas.courses import CourseCreate, CourseSummary

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseSummary])
def list_courses(db: DbSession) -> list[CourseSummary]:
    """Dersler; öğrenci ders seçerek başlar."""
    return service.list_courses(db)


@router.post("", response_model=CourseSummary, status_code=status.HTTP_201_CREATED)
def create_course(data: CourseCreate, db: DbSession) -> CourseSummary:
    """Yeni ders. Her dersin materyali ve araması diğerlerinden ayrıdır."""
    try:
        return service.create_course(db, data)
    except service.CourseExists as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{data.code} kodlu bir ders zaten var."
        ) from exc
