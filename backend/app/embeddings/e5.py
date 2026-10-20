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

    @property
    def identity(self) -> str:
        # Önek ya da normalizasyon değişirse sürüm artırılır: eski vektörler yeniden üretilmeli.
        return f"e5/{self.model_name}/v1"

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        for index, text in enumerate(texts):
            count = self.count_passage_tokens(text)
            if count > self.max_passage_tokens:
                raise ValueError(
                    f"Passage {index} exceeds the embedding token budget: "
                    f"{count} > {self.max_passage_tokens}. Re-ingest the source to split it."
                )
        return self._encode([f"passage: {text}" for text in texts])

    @property
    def max_passage_tokens(self) -> int:
        model = _load(self.model_name)
        return min(model.max_seq_length, model.tokenizer.model_max_length)

    def count_passage_tokens(self, text: str) -> int:
        return len(
            _load(self.model_name).tokenizer.encode(
                f"passage: {text}", add_special_tokens=True, truncation=False
            )
        )

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]

    def _encode(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = _load(self.model_name).encode(
            texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True
        )
        return vectors.tolist()
