from app.schemas.courses import CourseSummary


def list_courses(user_id: int) -> list[CourseSummary]:
    """Kullanıcının kayıtlı olduğu dersler ve her derste rolü."""
    raise NotImplementedError
