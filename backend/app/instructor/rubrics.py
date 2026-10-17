from app.schemas.rubrics import Rubric, RubricIn


def create_rubric(course_id: int, rubric: RubricIn) -> Rubric:
    """Rubriği ve referans cevabı kaydet; değerlendirmede soruyla birlikte getirilir."""
    raise NotImplementedError


def list_rubrics(course_id: int) -> list[Rubric]:
    raise NotImplementedError
