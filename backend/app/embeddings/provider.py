from app.core.config import settings
from app.embeddings.base import Embedder
from app.embeddings.e5 import E5Embedder
from app.embeddings.fake import FakeEmbedder


def get_embedder() -> Embedder:
    """Ayardaki sağlayıcı: "e5" (yerel model) ya da "fake" (testler)."""
    if settings.embedding_provider == "fake":
        return FakeEmbedder()
    return E5Embedder(settings.embedding_model)
