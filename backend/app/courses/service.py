from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
from app.schemas.courses import CourseCreate, CourseSummary


class CourseExists(ValueError):
    pass


def list_courses(db: Session) -> list[CourseSummary]:
    """Tüm dersler. Kimlik doğrulama gelince kullanıcının kayıtlı olduğu derslerle sınırlanacak."""
    return [to_summary(course) for course in db.scalars(select(Course).order_by(Course.code))]


def create_course(db: Session, data: CourseCreate) -> CourseSummary:
    if db.scalar(select(Course).where(Course.code == data.code)) is not None:
        raise CourseExists(data.code)
    course = Course(code=data.code, name=data.name, language=data.language)
    db.add(course)
    db.commit()
    return to_summary(course)


def to_summary(course: Course) -> CourseSummary:
    return CourseSummary(id=course.id, code=course.code, name=course.name, language=course.language)
