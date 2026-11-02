# İşletim notları

Bu belge sistemin işletim sınırlarını, uzun işlerin nasıl çalıştığını ve bir şey ters gittiğinde ne yapılacağını
anlatır (#21). Teslim ve kurulum el kitabı (#61) bu belgenin üzerine kurulacak.

## Süreçler

| Servis | Komut | Görev |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | Veritabanı ve iş kuyruğu (`processing_jobs`) |
| `api` | `uvicorn app.main:app` | HTTP API. Açılışta migration ve tohum verisi. `JOB_WORKER=external` iken uzun iş çalıştırmaz |
| `worker` | `python -m app.jobs.worker` | Kuyruktaki uzun işleri (transkripsiyon) çalıştırır (ADR-9) |
| `web` | Vite | Arayüz |

Birden çok `worker` aynı veritabanında güvenle çalışabilir: iş `FOR UPDATE SKIP LOCKED` ile alınır.

## Sınırlar

| Sınır | Değer | Ayar | Aşılınca |
|---|---|---|---|
| PDF/PPTX/VTT dosyası | 50 MB | `pipeline.MAX_UPLOAD_BYTES` (sabit) | `422`, kayıt ve dosya kalmaz |
| Medya dosyası (video/ses) | 2 GB | `MAX_MEDIA_BYTES` | `422`, kayıt ve dosya kalmaz |
| Yükleme isteğinin gövdesi | medya sınırı + 1 MB | `MAX_MEDIA_BYTES` | `413 file_too_large`, gövde okunmaz |
| Diğer isteklerin gövdesi (JSON) | 2 MB | `MAX_REQUEST_BYTES` | `413 file_too_large` |
| Dosya adı / başlık | 300 karakter | sabit | `422` |
| Medya adresi (`media_url`) | 1000 karakter, yalnızca https | sabit | `422` |
| Bir işin deneme sayısı | 2 | `JOB_MAX_ATTEMPTS` | Doküman `failed`, medya silinir |
| İş canlılık aralığı | 15 sn | `JOB_HEARTBEAT_INTERVAL_S` | — |
| İşin sahipsiz sayılması | 120 sn sessizlik | `JOB_STALE_AFTER_S` | Yeniden kuyruğa alınır ya da başarısız olur |
| Kuyruk yoklama aralığı | 2 sn | `JOB_POLL_INTERVAL_S` | — |

Gövde sınırı istek okunurken uygulanır (`app/core/limits.py`): çok parçalı form uç fonksiyondan önce geçici dosyaya
yazıldığı için sınır orada denetlenirse sınırı aşan dosya da diske yazılmış olurdu. Önde bir ters vekil (nginx vb.)
varsa onun gövde sınırı da en az medya sınırı kadar olmalı.

Ölçülmemiş değerler: transkripsiyon süresi (CPU'da `large-v3-turbo` ile 1 saatlik ders "dakikalar", ölçüm yok) ve
`worker`'ın bellek kullanımı (embedding modeli + whisper modeli). Pilot öncesi gerçek ders kaydıyla ölçülmeli.

## İş durumları

Doküman: `processing → ready | failed`. İş (`processing_jobs.status`):

| Durum | Anlamı |
|---|---|
| `queued` | Yüklendi, çalıştırıcıyı bekliyor. Medya `data/uploads/<ders>/<doküman>.<uzantı>` |
| `running` | Bir çalıştırıcı çalıştırıyor; `heartbeat_at` en çok 15 sn eski olmalı |
| `succeeded` | Transkript `<doküman>.vtt` olarak yazıldı, medya silindi |
| `failed` | Kalıcı hata ya da deneme hakkı bitti; `error` nedeni yazar, doküman `failed`, dosyalar silindi |
| `cancelled` | Eğitmen iptal etti; doküman `failed`, dosyalar silindi |

Bakmak için:

```bash
docker compose exec db psql -U learning learning_assistant -c "SELECT id, document_id, status, attempts, error, heartbeat_at FROM processing_jobs ORDER BY id DESC LIMIT 20"
```

## Kurtarma

- **`worker` ya da `api` yeniden başladı, iş yarıda kaldı.** Bir şey yapmak gerekmez. Medya diskte kaldığı için iş
  120 sn sonra yeniden kuyruğa alınır ve baştan çalışır. İkinci deneme de yarıda kalırsa doküman "İşlem yarıda kaldı"
  ile `failed` olur; eğitmen dosyayı yeniden yükler.
- **Doküman uzun süre "İşleniyor".** Önce `worker`'ın çalıştığını ve günlüğünü kontrol edin
  (`docker compose logs worker`). `queued` bekleyen iş varsa ve çalıştırıcı yoksa `docker compose up -d worker`.
  İşi durdurmak için `POST /api/documents/{id}/cancel` ile iptal edin (arayüzde düğme henüz yok).
- **Veritabanı bağlantısı koptu.** Çalıştırıcı hatayı günlüğe yazar ve yoklamaya devam eder. Bağlantı gelince süren iş
  canlılık yazamadıysa yukarıdaki gibi yeniden denenir.
- **Disk doldu.** Medya parça parça yazılır. Yazma hatası yüklemeyi `5xx` ile bitirir; kayıt geri alınır ve yarım dosya
  silinir. Yer açıp yeniden yükleyin. Kalmış dosya olup olmadığına bakmak için: dokümanı olmayan
  `data/uploads/<ders>/<id>.*` dosyaları güvenle silinebilir.
- **Migration.** Şema yalnızca `alembic upgrade head` ile değişir (api açılışında çalışır). CI her PR'da boş bir
  veritabanında `upgrade head`, `alembic check` (modellerle migration'lar aynı mı), `downgrade base` ve yeniden
  `upgrade head` çalıştırır.

## Temiz başlangıç denetimi

```bash
docker compose down -v          # veritabanı ve model hacimleri silinir
docker compose up --build
```

Beklenen: `api` migration'ları uygular, demo dersini oluşturur, embedding modelini indirir. `worker`, `api`'den sonra
başlar ve "İş çalıştırıcısı başladı" yazar. `TRANSCRIPTION_MODEL` boşsa medya yüklemesi `422` ile reddedilir; `.vtt`,
PDF ve PPTX yüklenir.
