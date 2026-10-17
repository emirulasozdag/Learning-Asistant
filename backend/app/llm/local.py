from pydantic import BaseModel


class LocalLLMClient:
    """Local model: gizli / offline / düşük maliyetli işler."""

    name = "local"

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T:
        raise NotImplementedError
