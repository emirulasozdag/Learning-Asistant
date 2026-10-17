from app.schemas.evaluation import AnswerFeedback
from app.schemas.learning import LearningRecord


def record_attempt(user_id: int, item_id: int, answer: str, feedback: AnswerFeedback) -> None:
    """Değerlendirilen denemeyi kaydet (yalnızca opt-in)."""
    raise NotImplementedError


def get_learning_record(user_id: int, course_id: int) -> LearningRecord:
    raise NotImplementedError
