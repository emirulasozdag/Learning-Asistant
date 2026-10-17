"""Hybrid retrieval — seçili derse ait kaynak parçalarını getirir (sunum slayt 11, 12).

Sorumluluk: multilingual-e5 dense arama + PostgreSQL full-text arama,
reciprocal rank fusion, opsiyonel cross-encoder rerank; ders filtresi aramadan
önce uygulanır; "bu adım" sorularında duraklatılan video zamanına yumuşak öncelik.

Henüz uygulanmadı.
"""
