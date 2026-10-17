from app.llm.base import LLMClient
from app.routing.router import TaskType


def select_client(task: TaskType, sensitive: bool, confidence: float | None = None) -> LLMClient:
    """Kural tabanlı seçim: hassas / rutin → local; karmaşık / düşük güven → hosted."""
    raise NotImplementedError


def select_judge_client() -> LLMClient:
    """Claim kontrolü için generator'dan farklı model ailesi."""
    raise NotImplementedError
