# evaluation/

Değerlendirme seti ve metrikler. Ayrıntılı plan: [docs/ANALYSIS.md §9](../docs/ANALYSIS.md#9-değerlendirme-planı-slayt-13).

**Durum (#8, #13):** Gold set / envanter şemaları, doğrulayıcı ve Q&A baseline koşucusu (#8); insan etiketleme
akışı, judge, κ ile kalibrasyon ve güvenilirlik raporu (#13) hazır. Judge gerektirmeyen metrikler (Recall@5,
kapsam, alıntı varlığı ve kapsamı, gecikme) her koşuda hesaplanıyor; doğruluk ve hallucination insan/judge
etiketinden gelir. Pilot dersin (BLM2512) gerçek girdileri henüz yok; eksikler
[`gold_sets/BLM2512/manifest.json`](gold_sets/BLM2512/manifest.json) içinde `missing_inputs` olarak, #13'ün
yapılamayan kısımları aşağıda [Açık boşluklar](#açık-boşluklar) altında.

## Klasörler

| Klasör | İçerik | Git'e girer mi? |
|---|---|---|
| `gold_sets/<DERS>/` | `manifest.json` (onaylı materyal envanteri) ve `gold_set.json` (sorular, referans cevaplar, kanıt konumları) | Evet. Ders içeriği değil, yalnızca parmak izi, sayfa ve soru/cevap |
| `harness/` | Şemalar, doğrulayıcı, koşucu, metrikler, etiketleme, judge, uyum, güvenilirlik raporu | Evet |
| `tests/` | Harness birim testleri (veritabanısız, sahte judge). Veritabanlı test: `backend/tests/test_eval_harness.py` | Evet |
| `rubrics/` | Cevap puanı ve iddia etiketi rubriği ([`qa_answer_and_claims.md`](rubrics/qa_answer_and_claims.md)) | Evet |
| `human_labels/` | Örneklem, değerlendirici etiketleri, judge kalibrasyonu; metin yok, takma ad ([README](human_labels/README.md)) | Evet, anonim |
| `instruments/` | Etiketleme birimleri, değerlendirici iş yükü, pilot formları ([README](instruments/README.md)) | Evet |
| `runs/` | Koşu kayıtları, etiketleme tabloları, judge etiketleri, raporlar (cevap ve pasaj metni ders içeriği barındırır) | Hayır (gitignore) |

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
  SHA-256'sı, sistem prompt'unun SHA-256'sı, LLM sağlayıcı/model, embedding modeli, retrieval ayarları,
  indeksteki dokümanların parmak izleri ve her soruda getirilen pasajların metni (judge ve değerlendiriciler
  iddiaları buna göre etiketler). `runs/<run_id>.md` okunabilir özettir.
- Hesaplanamayan her metrik değer yerine **boşluk** olarak yazılır (payda sıfır, judge kalibre değil,
  eksik girdi). Skor uydurulmaz.
- `--files-root`: veritabanındaki göreli dosya yollarının kökü. Varsayılan `..` (repo kökü,
  docker-compose'un `./data` bağlaması).
## Dört koşul (#18)

```bash
# Dört koşul aynı sorular, aynı üretici model ve aynı indeksle (tek parmak izi) koşulur.
python -m harness.run --gold gold_sets/BLM2512/gold_set.json --split heldout \
    --condition all --files-root .. --out runs/
# Tek ya da birkaç koşul: --condition full  |  --condition no_rag basic_rag
```

| Koşul | Arama | Kapı | Alıntı doğrulama / iddia kontrolü | Oynatma konumu |
|---|---|---|---|---|
| `no_rag` | yok | yok | yok (alıntısız) | yok |
| `basic_rag` | yalnız anlamsal, ilk 5 | yok | yok (etiketler yalnızca kaynağa çevrilir) | yok |
| `full` | hibrit + RRF | var | var (ürün hattı, `/ask`) | yok |
| `full_video_time` | hibrit + RRF + video komşuları | var | var | gold sorudaki `playback` |

- `no_rag` ve `basic_rag` karşılaştırma için minimal hatlardır (`harness/conditions.py`); ürün davranışı değildir.
  İkisi de LLM olmadan koşulamaz.
- Her koşu kaydı koşulun ayarlarını (`config.condition_settings`) ve ortak `batch_id`'yi taşır; batch için
  `runs/<batch_id>.compare.md` yan yana metrik tablosu yazılır. Model, indeks, embedder ya da sorular koşullar
  arasında farklıysa tablo "geçersiz karşılaştırma" uyarısı taşır.
- Tüm koşullar aynı gold kanıtına göre denetlenir (Recall@5, alıntı kapsamı/isabeti). `no_rag`'de arama ve alıntı
  yoktur: bu metrikler 0 değil boşluk olarak yazılır. Doğruluk ve hallucination her koşu kaydı için ayrı ayrı
  `harness.trust` / etiketleme akışıyla hesaplanır.
- `full_video_time` için gold soruya oynatma konumu eklenir: `"playback": {"document_sha256": "…", "time_s": 754}`
  (öğrencinin durdurduğu video ve an; video envanterde onaylı olmalı). Konumu olmayan sorular `full` ile aynı
  koşulur ve sayısı boşluk olarak yazılır.
- `verification_failure_rate`: cevabın iddia kontrolü yapılamadığı (#10, judge yok/hata) soruların oranı.

## Arama kalibrasyonu (#9)

```bash
# Yöntem karşılaştırması (yalnız anlamsal / yalnız kelime / hibrit, aday sayısı, RRF k) ve kapı ızgarası.
# LLM çağrılmaz. Eşik yalnızca calibration koşusunda önerilir; held-out yalnızca raporlanır.
python -m harness.retrieval_sweep --gold gold_sets/BLM2512/gold_set.json --split calibration \
    --files-root .. --out runs/ [--follow-ups takip.json]
```

- **Kapı:** soru, en iyi anlamsal benzerlik `RETRIEVAL_MIN_SIMILARITY` (0,78) ya da en iyi parçanın IDF
  ağırlıklı anahtar kelime kapsaması `RETRIEVAL_MIN_KEYWORD_COVERAGE` (0,5) üstündeyse dersle ilgili
  sayılır. Eskiden tek bir ortak kelime yetiyordu; ders dili `tr` olup materyal İngilizce olunca
  "what/is/the" her parçayla eşleşiyor ve her soru içeri alınıyordu.
- **Takip sorusu:** soru tek başına geçemezse önceki soruyla birlikte geçebilir, ama yalnızca kendi
  benzerliği `RETRIEVAL_FOLLOW_UP_MIN_SIMILARITY` (0,77) üstündeyse.
- **İndeks kimliği:** her parça kendi embedder kimliğiyle saklanır (`chunks.embedding_model`), anlamsal arama
  yalnızca etkin embedder'ın vektörlerini kullanır. Koşu kaydı `embedding_identity` ve `index_fingerprint`
  tutar. Model değişince ya da migration'dan sonra: `python -m app.scripts.reembed [--dry-run|--all]`.
- **Filtreli arama:** anlamsal arama ders içinde kesin (exact) yapılır; HNSW + ders filtresi küçük bir dersin
  adaylarını kaybediyordu (20 000 + 60 parçalık denemede 0 sonuç). Kelime aramasının IDF'i de yalnızca
  dersin parçalarından hesaplanır.

Ölçüm (2026-10-20, Git_1 notu, e5-base, LLM kapalı). **Taslak setler, eğitmen onayı yok:** kalibrasyon
seti ekip taslağı (20 cevaplanabilir + 12 kapsam dışı), held-out kullanıcının deneme seti (8 + 3).

| Set | Metrik | Önce | Sonra |
|---|---|---|---|
| Kalibrasyon | Recall@5 | 0,925 | 0,975 |
| | Kapsam dışı reddetme | 0,25 | 0,83 |
| | Aşırı reddetme | 0 | 0,05 |
| Held-out | Recall@5 | 0,75 | 0,875 |
| | Kapsam dışı reddetme | 0,67 | 1,00 |
| | Aşırı reddetme | 0 | 0 |

Yöntem karşılaştırması (kalibrasyon / held-out Recall@5): hibrit 0,97 / 0,88, yalnız anlamsal 0,93 / 0,81,
yalnız kelime 0,82 / 0,69. Aday sayısı 5→20 ve RRF k 60→20 fark yaratmadı. Aday recall'u Recall@5'e
eşit ya da çok yakın olduğu için reranker eklenmedi. Izgarada 0,79 eşiği kalibrasyonda kapsam dışı
reddetmeyi 0,92'ye çıkarıyor ama aşırı reddetmeyi tam sınıra (0,10) getiriyor; 20 soruda bu tek soruluk fark,
gerçek gold set gelene kadar 0,78 korundu.

Açık kalanlar: gerçek gold set (BLM2512, eğitmen incelemeli) yok, sayılar yalnızca taslak kanıt. Türkçe soru →
İngilizce not (held-out git-08) hâlâ kaçıyor: doğru sayfa anlamsal aramada 32. sırada, öndekiler yalnızca
başlıktan oluşan slaytlar; aynı soru İngilizce sorulunca 1. sırada. Çözüm ingestion (başlık-sadece slaytlar)
ya da daha güçlü çok dilli model; bu işte yapılmadı.

Bilinen tavizler: (1) Benzerliği 0,77–0,78 arasında kalan yeni bir soru, önceki soruyla birlikte kapıyı
geçebilir; taslak takip denemelerinde gerçek takip soruları da bu aralıkta (0,776–0,779). (2) Embedder
kimliği model adını içerir, model revizyonunu (ağırlık sürümü) içermez; aynı ad altında ağırlık
değişirse `--all` ile yeniden üretmek gerekir.

## İnsan etiketleri ve judge (#13)

Doğruluk ve hallucination etiket ister. Judge'a, insanlarla uyumu ölçülmeden güvenilmez. Kalibrasyon yalnızca
`calibration` split'inde yapılır; `heldout` judge ayarına hiç girmez, yalnızca raporlanır.

```bash
# 1. Kalibrasyon split'ini koş (her soruda getirilen pasajların metni kayda girer)
python -m harness.run --gold gold_sets/BLM2512/gold_set.json --split calibration --out runs/

# 2. Belgelenmiş örneklem ve boş etiketleme tablosu (tablo metin içerir, runs/ altında kalır)
python -m harness.labels sample --run runs/<run_id>.json --size 40 --seed 13
python -m harness.labels sheet --run runs/<run_id>.json --gold gold_sets/BLM2512/gold_set.json

# 3. En az iki değerlendirici tablonun kendi kopyasını bağımsız doldurur (rubrik: rubrics/), sonra:
python -m harness.labels import --run runs/<run_id>.json --sheet rater-a.csv --rater rater-a
python -m harness.labels import --run runs/<run_id>.json --sheet rater-b.csv --rater rater-b

# 4. Judge: generator'dan farklı aileden model; anahtar yoksa çalışmaz, puan uydurmaz
EVAL_JUDGE_MODEL=<openrouter-model-id> python -m harness.judge --run runs/<run_id>.json \
  --gold gold_sets/BLM2512/gold_set.json

# 5. Kalibrasyon: insan–insan ve judge–insan κ → human_labels/judge_calibration.json
python -m harness.judge_agreement --run runs/<run_id>.json --judge runs/<run_id>.judge.json

# 6. Güvenilirlik raporu → runs/<run_id>.trust.md (held-out için 1-4 tekrarlanır, 5 atlanır)
python -m harness.trust --run runs/<run_id>.json
```

- **Etiket şeması** ([`harness/labels.py`](harness/labels.py)): değerlendirici takma adı, cevap puanı 0/1/2,
  iddia başına `supported`/`unsupported` (rubrik: [`rubrics/qa_answer_and_claims.md`](rubrics/qa_answer_and_claims.md)).
  İddialar cevabın belirlenimci cümle bölmesiyle çıkar ([`harness/claims.py`](harness/claims.py)): herkes aynı
  birimi etiketler, iddia metninin SHA-256'sı saklanır. Tablo Excel için `;` ayraçlı ve BOM'lu UTF-8; virgüllü
  CSV de okunur. Eksik ya da geçersiz hücre varsa içe aktarma hepsini listeleyip durur.
- **Judge** ([`harness/judge.py`](harness/judge.py)): cevap puanı referans cevaba göre, iddia etiketi getirilen
  pasajlara göre; çıktı JSON şemasıyla, backend'in OpenRouter istemcisiyle. Ayarlar: `EVAL_JUDGE_MODEL`
  (zorunlu), `EVAL_JUDGE_API_KEY` (yoksa `LLM_API_KEY`), `EVAL_JUDGE_BASE_URL`. Judge'ın model ailesi
  generator'la aynıysa ya da tanınmıyorsa çalışmaz. Judge'ın cevap veremediği soru etiketsiz kalır ve boşluk
  olarak yazılır. Prompt'un parmak izi etiketlere yazılır; prompt değişirse eski kalibrasyon geçmez.
- **Uyum** ([`harness/judge_agreement.py`](harness/judge_agreement.py)): Cohen's κ (ağırlıksız), cevap puanı ve
  iddia etiketi için ayrı ayrı. Judge'ın otoriter sayılması için kalibrasyon split'inde en az 2 insan
  değerlendirici, insanlar arası κ ≥ 0,6, judge ile her insan arasında iki türde de κ ≥ 0,6 ve en az 40 ortak
  puanlı cevap gerekir. Rapordaki judge etiketleri de kalibre edilen model, prompt ve gold set sürümüyle
  üretilmiş olmalıdır.
- **Güvenilirlik raporu** ([`harness/trust.py`](harness/trust.py)): `harness.run` raporunun metrik tablosu
  (aynı adlar), her değerlendiricinin örneklem sonuçları, judge sonuçları, κ tablosu, anlaşmazlık listesi (soru
  id + iddia sırası; metin tablodadır) ve boşluklar. Judge otoriter değilse ana tablodaki doğruluk ve
  hallucination değer yerine "judge sonuçları otoriter değil" boşluğuyla yazılır; judge'ın sayıları ayrı
  tabloda "ön sonuç" olarak durur.

## Metrikler ve hedefler (hipotez)

| Boyut | Metrik | Hedef | Durum |
|---|---|---|---|
| Cevap doğruluğu | Tamamen doğru oranı: puanı 2 olan / hatasız cevaplanabilir soru (reddedilen 0 sayılır) | ≥ %80 | ✅ etiketten (insan örneklemi; judge kalibre ise tümü) |
| Hallucination | Desteklenmeyen iddia içeren cevap / cevaplanmış cevaplanabilir soru; iddia düzeyinde oran da | ≤ %10 | ✅ etiketten |
| Kapsam uyumu | Kapsam dışında reddetme / aşırı reddetme | ≥ %90 / ≤ %10 | ✅ hesaplanıyor |
| Retrieval | Recall@5 | ≥ 0,85 | ✅ hesaplanıyor |
| Pratik kalitesi | Kabul edilebilir item oranı | ≥ %85 | ✅ etiketten (`harness.pilot`) |
| Değerlendirme uyumu | Eğitmen skorlarıyla QWK | ≥ 0,70 | ✅ etiketten (`harness.pilot`) |
| Kullanılabilirlik | SUS; 5'li anket | ≥ 70; ≥ 4,0 | ✅ anketten (`harness.pilot`) |

İnsan örneklemi metrikleri (pratik kabulü, değerlendirme QWK'si, SUS, memnuniyet) koşu kaydından değil etiket
dosyalarından hesaplanır:

```bash
python -m harness.pilot --labels human_labels/pilot/BLM2512 --out runs/
```

Dosya biçimleri `harness/pilot.py`'de, örneklem birimleri, iş yükü ve formlar
[`instruments/README.md`](instruments/README.md)'de. Etiket yoksa ya da örneklem planlanandan küçükse metrik
değer yerine boşlukla yazılır.

Ek olarak her koşuda: cevaplanan sorularda alıntı varlığı, **alıntı kapsamı** (gold kanıtın alıntılarla
karşılanan oranı, soru başına ortalama), **alıntı isabeti** (gold kanıta düşen alıntı / tüm alıntı), sağlayıcı
hatası oranı, gecikme p50/p95. Her metrik paydasıyla yazılır.

Judge modeli generator'dan farklı bir model ailesinden seçilir. Judge'a yalnızca insanla uyumu **κ ≥ 0,6** ise güvenilir.

## Açık boşluklar

#13'ün şu kısımları dış girdi ya da başka iş bekliyor; değer uydurulmadı:

- **Gerçek insan etiketi yok.** İki bağımsız değerlendirici (takma adlı) gerekiyor; gold set gelmeden
  etiketlenecek koşu yok.
- **Eğitmen gold set'i yok** (BLM2512: ≥ 30 incelenmiş cevaplanabilir + ≥ 30 kapsam dışı soru, calibration /
  heldout ayrımıyla). Bkz. envanterdeki `missing_inputs`.
- **Judge modeli seçilmedi, anahtar yok** (`docs/DECISIONS.md`, açık soru 6). Kalibrasyon yapılmadı; judge
  sonuçları otoriter değil.
- **İlk güvenilirlik raporu ve son baseline**, S02-A/B (#9, #10) entegrasyonundan sonra gerçek materyalle
  koşulacak. M1 kabul kanıtı ve iyileştirme issue'ları o rapordan çıkacak.
- **Maliyet kaydı yok:** soru-cevap hattı token kullanımını döndürmüyor; koşu kaydı bunu boşluk olarak yazar.
  Gecikme (p50/p95) kaydediliyor.

#18'in dış girdi bekleyen kısımları (değer uydurulmadı; envanterde `missing_inputs`):

- **150 eğitmen referanslı soru + 30 kapsam dışı soru** ve kanıt konumları (şu an 0). Dört koşulun gerçek
  karşılaştırması bu set gelince koşulur.
- **İnsan örneklemleri:** 40 pratik sorusu incelemesi, 60 öğrenci cevabının kör puanlaması, ≥ 20 onaylı gönüllünün
  anketi. Pilot öncesi etik/bölüm onayı ve aydınlatma metninin son sürümü (ADR-4) gerekiyor.
- **SUS'un Türkçe uyarlaması** seçilip formun sürümü sabitlenmeli (`instruments/README.md`).

## CI

Backend işi `TEST_DATABASE_URL` ile tek kullanımlık bir PostgreSQL servisinde koşar. `REQUIRE_DB_TESTS=1`
olduğu için veritabanı testleri sessizce atlanamaz. Test veritabanının adı `_test` ile bitmek zorundadır, çünkü
tablolar her testte boşaltılır. Harness birim testleri ayrı adımda koşar (`pytest ../evaluation/tests`).
