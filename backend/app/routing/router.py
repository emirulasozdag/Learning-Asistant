from dataclasses import dataclass
from enum import StrEnum


class TaskType(StrEnum):
    ASK = "ask"
    PRACTICE = "practice"
    EVALUATE = "evaluate"


@dataclass
class RoutedTask:
    task: TaskType
    course_id: int
    video_window_s: tuple[float, float] | None = None


def route(task: TaskType, course_id: int, video_time_s: float | None = None) -> RoutedTask:
    """Görevi ders filtresi ve opsiyonel video penceresiyle ilgili akışa yönlendir."""
    raise NotImplementedError
