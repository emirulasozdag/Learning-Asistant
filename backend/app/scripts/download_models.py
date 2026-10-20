"""Embedding modelini (ve TRANSCRIPTION_MODEL doluysa transkripsiyon modelini) önceden indirir.

Embedding ~1 GB, large-v3-turbo ~1,6 GB; bir kez indirilir, sonrası internetsiz çalışır.

Kullanım: python -m app.scripts.download_models
"""

from app.core.config import settings
from app.embeddings.provider import get_embedder
from app.ingestion.transcribe import load_model


def main() -> None:
    if settings.embedding_provider != "e5":
        print(f"Embedding sağlayıcısı '{settings.embedding_provider}'; indirilecek model yok.")
    else:
        print(f"Model hazırlanıyor: {settings.embedding_model}")
        vector = get_embedder().embed_query("hazır mı?")
        print(f"Hazır ({len(vector)} boyut).")
    if settings.transcription_model:
        print(f"Transkripsiyon modeli hazırlanıyor: {settings.transcription_model}")
        load_model(settings.transcription_model)
        print("Hazır.")


if __name__ == "__main__":
    main()
