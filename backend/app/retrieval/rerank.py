from app.retrieval.types import RetrievedPassage


def rerank(query: str, passages: list[RetrievedPassage], top_k: int) -> list[RetrievedPassage]:
    """Opsiyonel cross-encoder reranker (top-k precision).

    Eklenmedi: taslak setlerde aday recall'u Recall@5'e eşit ya da çok yakın (kalibrasyon
    1.00 / 0.97, held-out 0.88 / 0.88); yeniden sıralamanın kazandırabileceği soru yok denecek
    kadar az. Gerçek gold set'te bu fark açılırsa ölçülerek eklenir (#9).
    """
    raise NotImplementedError
