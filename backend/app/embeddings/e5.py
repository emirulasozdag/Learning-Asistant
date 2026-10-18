import threading

from app.embeddings.base import EMBEDDING_DIM

# Model ilk kullanımda bir kez yüklenir (~1 GB); sonraki çağrılar aynı örneği kullanır.
_lock = threading.Lock()
_models: dict[str, object] = {}


def _load(model_name: str):
    with _lock:
        if model_name not in _models:
            # Ağır bağımlılık: yalnızca gerçekten gerektiğinde içe aktar.
            from sentence_transformers import SentenceTransformer

            _models[model_name] = SentenceTransformer(model_name, device="cpu")
        return _models[model_name]


class E5Embedder:
    """multilingual-e5: Türkçe/İngilizce ders metni. E5, `query:` / `passage:` önekleri ister."""

    name = "e5"
    dim = EMBEDDING_DIM

    def __init__(self, model_name: str, batch_size: int = 16) -> None:
        self.model_name = model_name
        self.batch_size = batch_size

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {text}" for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = _load(self.model_name).encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()
