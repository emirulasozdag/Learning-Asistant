from typing import Protocol

from pydantic import BaseModel


class LLMClient(Protocol):
    """Tüm sağlayıcılar aynı arayüzü ve aynı JSON-schema çıktısını kullanır."""

    name: str

    def complete_json[T: BaseModel](self, prompt: str, schema: type[T]) -> T: ...
