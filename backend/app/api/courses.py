from fastapi import APIRouter, HTTPException, status

from app.api.deps import DbSession, get_course_or_404
from app.courses import service
from app.schemas.courses import CourseCreate, CourseOutline, CourseSummary, CourseUpdate

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


@router.patch("/{course_id}", response_model=CourseSummary)
def update_course(course_id: int, data: CourseUpdate, db: DbSession) -> CourseSummary:
    """Ders bilgisini düzenler (eğitmen, dönem, seviye, bölüm, açıklama, ad, dil)."""
    return service.update_course(db, get_course_or_404(db, course_id), data)


@router.get("/{course_id}/outline", response_model=CourseOutline)
def course_outline(course_id: int, db: DbSession) -> CourseOutline:
    """Dersin izlencesi ve takvimi (OCW "Syllabus" / "Calendar")."""
    course = get_course_or_404(db, course_id)
    return CourseOutline.model_validate({"syllabus": course.syllabus, "calendar": course.calendar})
