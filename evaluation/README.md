# evaluation/

Değerlendirme seti ve metrikler. Ayrıntılı plan: [docs/ANALYSIS.md §9](../docs/ANALYSIS.md#9-değerlendirme-planı-slayt-13).
`harness/` altında 7 metrik ve 4 koşulun iskeleti var; mantık henüz yok (WP13).

## Klasörler

| Klasör | İçerik | Git'e girer mi? |
|---|---|---|
| `gold_sets/` | 150 test sorusu, eğitmen referans cevapları, gold kanıt pasaj ID'leri, 30 kapsam dışı soru | Evet, yalnızca anonim / şema düzeyinde |
| `rubrics/` | Cevap değerlendirme ve pratik soru inceleme rubrikleri | Evet |
| `human_labels/` | Değerlendirici etiketleri (cevap 0/1/2, iddia supported/unsupported, item kabul, öğrenci cevabı notu) | Evet, anonim |
| `runs/` | Otomatik değerlendirme koşularının çıktıları | Hayır (gitignore) |

## Metrikler ve hedefler (hipotez)

| Boyut | Metrik | Hedef |
|---|---|---|
| Cevap doğruluğu | Tamamen doğru oranı (4 koşul: no RAG · basic RAG · full · full + video time) | ≥ %80 |
| Hallucination | Desteklenmeyen iddia içeren cevap oranı | ≤ %10 |
| Kapsam uyumu | Kapsam dışında reddetme / aşırı reddetme | ≥ %90 / ≤ %10 |
| Retrieval | Recall@5 | ≥ 0,85 |
| Pratik kalitesi | Kabul edilebilir item oranı | ≥ %85 |
| Değerlendirme uyumu | Eğitmen skorlarıyla QWK | ≥ 0,70 |
| Kullanılabilirlik | SUS; 5'li anket | ≥ 70; ≥ 4,0 |

Judge modeli generator'dan farklı bir model ailesinden seçilir. Judge'a yalnızca insanla uyumu **κ ≥ 0,6** ise güvenilir.
