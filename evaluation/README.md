# evaluation/

Değerlendirme seti ve metrikler. Ayrıntılı plan: [docs/ANALYSIS.md §9](../docs/ANALYSIS.md#9-değerlendirme-planı-slayt-13).

**Durum (#8):** Gold set / envanter şemaları, doğrulayıcı ve Q&A baseline koşucusu hazır. Judge gerektirmeyen
metrikler (Recall@5, kapsam, alıntı varlığı, gecikme) hesaplanıyor; doğruluk ve hallucination #13'te judge
kalibre edilince gelecek. Pilot dersin (BLM2512) gerçek girdileri henüz yok; eksikler
[`gold_sets/BLM2512/manifest.json`](gold_sets/BLM2512/manifest.json) içinde `missing_inputs` olarak kayıtlı.

## Klasörler

| Klasör | İçerik | Git'e girer mi? |
|---|---|---|
| `gold_sets/<DERS>/` | `manifest.json` (onaylı materyal envanteri) ve `gold_set.json` (sorular, referans cevaplar, kanıt konumları) | Evet. Ders içeriği değil, yalnızca parmak izi, sayfa ve soru/cevap |
| `harness/` | Şemalar, doğrulayıcı, koşucu, metrikler | Evet |
| `tests/` | Harness birim testleri (veritabanısız). Veritabanlı test: `backend/tests/test_eval_harness.py` | Evet |
| `rubrics/` | Cevap değerlendirme ve pratik soru inceleme rubrikleri | Evet |
| `human_labels/` | Değerlendirici etiketleri (cevap 0/1/2, iddia supported/unsupported, item kabul, öğrenci cevabı notu) | Evet, anonim |
| `runs/` | Koşu çıktıları (cevap metinleri ders içeriği barındırır) | Hayır (gitignore) |

## Girdi şemaları

Tanım: [`harness/schemas.py`](harness/schemas.py). Bilinmeyen alan reddedilir.

**Kaynak konumu.** Chunk id'leri her yüklemede değiştiği için kanıt, **dosyanın SHA-256'sı** ve
**sayfa** (PDF/PPTX) ya da **video aralığı** (`t_start`/`t_end`, saniye) ile gösterilir. Pasaj metni dosyalara
yazılmaz. Sistemin getirdiği parça, aynı dokümanda aynı sayfadaysa ya da zaman aralığı kesişiyorsa
kanıtla eşleşir. Dosyanın parmak izi: `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" dosya.pdf`

**Envanter (`manifest.json`).** Her doküman `approved` (izin kaydı zorunlu) ya da `excluded` (gerekçe zorunlu;
ör. aktif sınav). İndekste envanterde onaylı olmayan bir doküman varsa koşu çalışmaz. `approved_by` eğitmen
onayıdır (kişisel veri yerine rol/takma ad). `missing_inputs` henüz elde olmayan dış girdiler içindir.

**Gold set (`gold_set.json`).** Her soru:

```json
{
  "id": "bs-01",
  "split": "heldout",
  "kind": "answerable",
  "question": "…",
  "reference_answer": "…",
  "evidence": [{"document_sha256": "<64 hex>", "page": 2}],
  "origin": "instructor",
  "review": {"reviewer": "instructor-1", "reviewed_at": "2026-10-27T10:00:00Z"}
}
```

- `split`: `calibration` (eşik/prompt ayarı) ya da `heldout` (yalnızca ölçüm). Aynı soru iki sette olamaz.
- `kind`: `answerable` (kanıt ve referans cevap zorunlu) ya da `out_of_scope` (kanıt ve referans cevap olmaz).
- `origin`: `instructor`, `past_exam` ya da `team_draft`. Eğitmen incelemesi (`review`) olmayan soru varsayılan
  olarak koşulmaz. **Örnek uydurulmaz**: referans cevap ve kanıt eğitmenden ya da eğitmenin onayladığı
  materyalden gelir.

## Kullanım

`backend` kurulu olmalı (`pip install -e "backend[dev]"`). Komutlar `evaluation/` içinden:

```bash
# Şema + tutarlılık + eksikler (ör. 30'dan az incelenmiş soru). --strict: eksik varsa çıkış kodu 2
python -m harness.validate gold_sets/BLM2512/gold_set.json

# Baseline koşusu. Veritabanında ders ve materyal yüklü olmalı (docker compose).
DATABASE_URL=postgresql+psycopg://learning:learning@localhost:5432/learning_assistant \
  python -m harness.run --gold gold_sets/BLM2512/gold_set.json --split heldout --out runs/
```

- Her soru gerçek soru-cevap hattından geçer (hibrit arama, LLM, alıntı doğrulama) ve **geri alınan bir
  veritabanı işleminde** sorulur: koşu sohbet/mesaj kaydı bırakmaz, eğitmen analitiğini kirletmez.
- Koşu kaydı (`runs/<run_id>.json`) şunları tutar: commit ve çalışma ağacının temizliği, gold set ve envanter
  SHA-256'sı, sistem prompt'unun SHA-256'sı, LLM sağlayıcı/model, embedding modeli, retrieval ayarları ve
  indeksteki dokümanların parmak izleri. `runs/<run_id>.md` okunabilir özettir.
- Hesaplanamayan her metrik değer yerine **boşluk** olarak yazılır (payda sıfır, judge kalibre değil,
  eksik girdi). Skor uydurulmaz.
- `--files-root`: veritabanındaki göreli dosya yollarının kökü. Varsayılan `..` (repo kökü,
  docker-compose'un `./data` bağlaması).
- Şimdilik yalnızca `full` koşulu var; `no_rag`, `basic_rag` ve `full_video_time` sonraki işlerde.

## Metrikler ve hedefler (hipotez)

| Boyut | Metrik | Hedef | Durum |
|---|---|---|---|
| Cevap doğruluğu | Tamamen doğru oranı (4 koşul: no RAG · basic RAG · full · full + video time) | ≥ %80 | judge gerekli (#13) |
| Hallucination | Desteklenmeyen iddia içeren cevap oranı | ≤ %10 | judge gerekli (#13) |
| Kapsam uyumu | Kapsam dışında reddetme / aşırı reddetme | ≥ %90 / ≤ %10 | ✅ hesaplanıyor |
| Retrieval | Recall@5 | ≥ 0,85 | ✅ hesaplanıyor |
| Pratik kalitesi | Kabul edilebilir item oranı | ≥ %85 | — |
| Değerlendirme uyumu | Eğitmen skorlarıyla QWK | ≥ 0,70 | — |
| Kullanılabilirlik | SUS; 5'li anket | ≥ 70; ≥ 4,0 | — |

Ek olarak her koşuda: cevaplanan sorularda alıntı varlığı, sağlayıcı hatası oranı, gecikme p50/p95.
Maliyet henüz kaydedilmiyor (soru-cevap hattı token kullanımını döndürmüyor).

Judge modeli generator'dan farklı bir model ailesinden seçilir. Judge'a yalnızca insanla uyumu **κ ≥ 0,6** ise güvenilir.

## CI

Backend işi `TEST_DATABASE_URL` ile tek kullanımlık bir PostgreSQL servisinde koşar. `REQUIRE_DB_TESTS=1`
olduğu için veritabanı testleri sessizce atlanamaz. Test veritabanının adı `_test` ile bitmek zorundadır, çünkü
tablolar her testte boşaltılır. Harness birim testleri ayrı adımda koşar (`pytest ../evaluation/tests`).
