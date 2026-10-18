from typing import Protocol

from app.db.models import EMBEDDING_DIM

__all__ = ["EMBEDDING_DIM", "Embedder"]


class Embedder(Protocol):
    """Parçalar ve sorular aynı uzaya, birim uzunlukta vektörlerle gömülür."""

    name: str
    dim: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
