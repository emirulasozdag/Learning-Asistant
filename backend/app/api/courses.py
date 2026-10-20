from fastapi import APIRouter, status

from app.api.deps import DbSession, get_course_for
from app.api.errors import ApiError
from app.auth.dependencies import AuthUser, not_found_error
from app.courses import service
from app.schemas.auth import JoinCourseRequest
from app.schemas.courses import CourseCreate, CourseOutline, CourseSummary, CourseUpdate, JoinCode

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("", response_model=list[CourseSummary])
def list_courses(user: AuthUser, db: DbSession) -> list[CourseSummary]:
    """Kullanıcının üye olduğu dersler ve oradaki rolü."""
    return service.list_courses(db, user.id)


@router.post("", response_model=CourseSummary, status_code=status.HTTP_201_CREATED)
def create_course(data: CourseCreate, user: AuthUser, db: DbSession) -> CourseSummary:
    """Yeni ders; açan kullanıcı eğitmeni olur. Yalnızca ders açma yetkisi olan hesaplar
    (eğitmen hesapları, ADR-1) açabilir."""
    if not user.user.can_create_courses:
        raise ApiError(status.HTTP_403_FORBIDDEN, "Ders açma yetkiniz yok", "insufficient_role")
    try:
        return service.create_course(db, data, user.user)
    except service.CourseExists as exc:
        raise ApiError(
            status.HTTP_409_CONFLICT, f"{data.code} kodlu bir ders zaten var.", "course_exists"
        ) from exc


@router.post("/join", response_model=CourseSummary)
def join_course(data: JoinCourseRequest, user: AuthUser, db: DbSession) -> CourseSummary:
    """Katılım koduyla derse öğrenci olarak katılır (ADR-2)."""
    try:
        return service.join_course(db, data.code, user.user)
    except service.InvalidJoinCode as exc:
        raise not_found_error("course_not_found") from exc


@router.patch("/{course_id}", response_model=CourseSummary)
def update_course(
    course_id: int, data: CourseUpdate, user: AuthUser, db: DbSession
) -> CourseSummary:
    """Ders bilgisini düzenler (eğitmen, dönem, seviye, bölüm, açıklama, ad, dil)."""
    course = get_course_for(db, user, course_id, "instructor")
    return service.update_course(db, course, data, "instructor")


@router.get("/{course_id}/join-code", response_model=JoinCode)
def get_join_code(course_id: int, user: AuthUser, db: DbSession) -> JoinCode:
    """Dersin katılım kodu; yalnızca eğitmen görür."""
    return service.join_code(db, get_course_for(db, user, course_id, "instructor"))


@router.post("/{course_id}/join-code", response_model=JoinCode)
def rotate_join_code(course_id: int, user: AuthUser, db: DbSession) -> JoinCode:
    """Katılım kodunu yeniler; eski kod geçersiz olur. Var olan üyelikler etkilenmez."""
    return service.rotate_join_code(db, get_course_for(db, user, course_id, "instructor"))


@router.get("/{course_id}/outline", response_model=CourseOutline)
def course_outline(course_id: int, user: AuthUser, db: DbSession) -> CourseOutline:
    """Dersin izlencesi ve takvimi (OCW "Syllabus" / "Calendar"); dersin her üyesi görür."""
    course = get_course_for(db, user, course_id)
    return CourseOutline.model_validate({"syllabus": course.syllabus, "calendar": course.calendar})
