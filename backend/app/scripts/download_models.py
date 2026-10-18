"""Embedding modelini önceden indirir (bir kez ~1 GB). Sonrası internetsiz çalışır.

Kullanım: python -m app.scripts.download_models
"""

from app.core.config import settings
from app.embeddings.provider import get_embedder


def main() -> None:
    if settings.embedding_provider != "e5":
        print(f"Embedding sağlayıcısı '{settings.embedding_provider}'; indirilecek model yok.")
        return
    print(f"Model hazırlanıyor: {settings.embedding_model}")
    vector = get_embedder().embed_query("hazır mı?")
    print(f"Hazır ({len(vector)} boyut).")


if __name__ == "__main__":
    main()
