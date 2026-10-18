"""Hybrid retrieval — seçili derse ait kaynak parçalarını getirir (sunum slayt 11, 12).

Sorumluluk: multilingual-e5 dense arama + PostgreSQL full-text arama,
reciprocal rank fusion, opsiyonel cross-encoder rerank; ders filtresi aramadan
önce uygulanır; "bu adım" sorularında duraklatılan video zamanına yumuşak öncelik.

Durum: hibrit arama çalışıyor — dense (`dense.py`, pgvector) + full-text (`lexical.py`)
→ RRF (`fusion.py`). Rerank ve video-zaman önceliği sonraki adım. Giriş: `hybrid.retrieve`.
"""
