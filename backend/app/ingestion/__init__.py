"""Ingestion — ders materyalini indekse hazırlar (sunum slayt 11, 14).

Sorumluluk: parse → clean → chunk; her parçaya sayfa / video-zaman metadata'sı.
Kaynaklar: ders notu, slayt, ders kitabı alıntısı, geçmiş sınav, ders transkripti.
Araçlar: PyMuPDF (PDF), python-pptx (PPTX). Sonraki adım: webvtt-py ve faster-whisper
ile transkriptler; embedding (dense arama için).

Giriş noktası: `pipeline.ingest_document`.
"""
