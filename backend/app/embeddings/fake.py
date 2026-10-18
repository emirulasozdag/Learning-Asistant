import hashlib
import math
import re

from app.embeddings.base import EMBEDDING_DIM

_WORD = re.compile(r"\w+", re.UNICODE)


class FakeEmbedder:
    """Testler ve CI için: model indirmeden, deterministik "kelime torbası" vektörü.

    Aynı kelimeleri paylaşan metinler birbirine yakın düşer; anlamsal benzerlik yoktur.
    """

    name = "fake"
    dim = EMBEDDING_DIM

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for word in _WORD.findall(text.lower()):
            index = int(hashlib.blake2b(word[:5].encode(), digest_size=4).hexdigest(), 16)
            vector[index % self.dim] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]
