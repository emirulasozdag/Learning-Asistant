# İşletim notları

Bu belge sistemin işletim sınırlarını, uzun işlerin nasıl çalıştığını ve bir şey ters gittiğinde ne yapılacağını
anlatır (#21). Teslim ve kurulum el kitabı (#61) bu belgenin üzerine kurulacak.

## Süreçler

| Servis | Komut | Görev |
|---|---|---|
| `db` | `pgvector/pgvector:pg16` | Veritabanı ve iş kuyruğu (`processing_jobs`) |
| `api` | `uvicorn app.main:app` | HTTP API. Açılışta migration ve tohum verisi. `JOB_WORKER=external` iken uzun iş çalıştırmaz |
| `worker` | `python -m app.jobs.worker` | Kuyruktaki uzun işleri (transkripsiyon, kare çıkarma, kare yorumlama) çalıştırır (ADR-9, ADR-11); sahipsiz dosyaları temizler |
| `web` | Vite | Arayüz |

Birden çok `worker` aynı veritabanında güvenle çalışabilir: iş `FOR UPDATE SKIP LOCKED` ile alınır.

## Sınırlar

| Sınır | Değer | Ayar | Aşılınca |
|---|---|---|---|
| PDF/PPTX/VTT dosyası | 50 MB | `pipeline.MAX_UPLOAD_BYTES` (sabit) | `422`, kayıt ve dosya kalmaz |
| Medya dosyası (video/ses) | 2 GB | `MAX_MEDIA_BYTES` | `422`, kayıt ve dosya kalmaz |
| Medya / altyazı süresi (#25, #125) | 1 saat | `MAX_MEDIA_DURATION_S` | Altyazı `422`; medya transkripsiyon başlamadan `failed`; kare videosu kare çıkarmadan önce `frames` işiyle `failed` |
| Yükleme isteğinin gövdesi | medya sınırı + 1 MB | `MAX_MEDIA_BYTES` | `413 file_too_large`, gövde okunmaz |
| Diğer isteklerin gövdesi (JSON) | 2 MB | `MAX_REQUEST_BYTES` | `413 file_too_large` |
| Dosya adı / başlık | 300 karakter | sabit | `422` |
| Medya adresi (`media_url`) | 1000 karakter, yalnızca https | sabit | `422` |
| Bir işin deneme sayısı | 2 | `JOB_MAX_ATTEMPTS` | Doküman `failed`, medya silinir |
| İş canlılık aralığı | 15 sn | `JOB_HEARTBEAT_INTERVAL_S` | — |
| İşin sahipsiz sayılması | 120 sn sessizlik | `JOB_STALE_AFTER_S` | Yeniden kuyruğa alınır ya da başarısız olur |
| Kuyruk yoklama aralığı | 2 sn | `JOB_POLL_INTERVAL_S` | — |
| Video başına kare (ADR-10) | 300 | sabit (`FrameParams.max_frames`) | Sonraki sahneler atlanır, günlüğe uyarı |
| Kare görüntüsü genişliği | 1920 px | sabit (`FrameParams.max_image_width`) | Küçültülür |
| Tek karenin OCR süresi | 120 sn | sabit (`ocr.TIMEOUT_S`) | Kare `unreadable` |

Gövde sınırı istek okunurken uygulanır (`app/core/limits.py`): çok parçalı form uç fonksiyondan önce geçici dosyaya
yazıldığı için sınır orada denetlenirse sınırı aşan dosya da diske yazılmış olurdu. Önde bir ters vekil (nginx vb.)
varsa onun gövde sınırı da en az medya sınırı kadar olmalı.

**Bellek ve süre sınırı (ölçüldü, #31).** Transkripsiyonun belleği medyanın süresiyle doğrusal büyür: faster-whisper
sesin tamamının özelliklerini tek seferde hesaplar. `tiny` ile saat başına ~3,7 GB (aşağıda "Kaynak kullanımı ve
süre"). `worker`'ın en yüksek belleği ≈ 1,2 GB (embedding modeli) + 3,7 GB × saat. `MAX_MEDIA_DURATION_S` bu yüzden
`worker`'a ayrılan belleğe göre seçilmeli. Varsayılan **1 saat** (#125; `worker` en çok ~5,3 GB). 16 GB'lık bir
makinede (Docker Desktop ~15,5 GB; `api` ~1 GB, `db`) 2 saate kadar çıkarılabilir (~9 GB); 4 saat ~16 GB ister ve
çalışmaz. Bellek yetmezse `worker` işletim sistemince öldürülür, iş yeniden denenir ve ikinci denemede de ölürse
doküman "İşlem yarıda kaldı" ile `failed` olur (veri bozulmaz, medya silinir). Sınırı kaldıracak çözüm: parçalı
transkripsiyon (#127).
Daha büyük modeller (`small`, `large-v3-turbo`) daha çok bellek ve süre ister; ölçülmedi.

**Kare adımı (`FRAME_EXTRACTION=ocr`, ADR-10, ADR-11).** Transkripsiyondan sonra ayrı bir `frames` işinde aynı medyadan
çalışır (medya o iş bitince silinir); doküman kareleri beklemeden `ready` olur. Kareler önce
`data/uploads/<ders>/frames/<doküman>.partial/`a yazılır, sonuç yazılınca `frames/<doküman>/` olur. Kare adımı yapılamazsa
(video çözülemedi, Tesseract yok) `frames` işi "Videodan slayt karesi çıkarılamadı." ile `failed` olur ve doküman karesiz
`ready` kalır. Doküman silinince ya da transkripsiyonu başarısız/iptal olunca kare klasörleri de silinir. Ölçülen: 720p sentetik slayt videosunda kare
seçimi örnek başına ~10 ms; OCR kare başına ~1 sn (üç okuma). Kendi kayıtlarımız (PowerPoint, 1080p, `tiny`): 86 sn'lik
Türkçe ders (5 slayt) ve 52 sn'lik İngilizce ders (5 slayt; İngilizce ve Türkçe derse ayrı ayrı yüklendi): slayt başına
bir kare, geçişler doğru; iş ~20 sn. 72 sn'lik zor durumlar kaydı (konuşmacı kamerası açık, koyu tema, madde madde
açılan slayt, küçük yoğun yazı, fotoğraf, 1 sn'den kısa slayt, aynı slayta dönüş): 9 kare; kamera sahneleri bölmedi,
her madde ayrı kare, fotoğraf `no_text`, kısa slayt atlandı, dönülen slayt ayrı kare; yoğun yazıda 7 satırdan ikisinin
ilk kelimesi eksik. Uzun gerçek ders kayıtlarında ölçülmedi.

## Kaynak kullanımı ve süre (#31)

Ölçüm aracı: `python -m app.scripts.measure_media`. Gerçek işlem hattının adımlarını (süre okuma, transkripsiyon,
transkript vektörleri, kare çıkarma, OCR, kare vektörleri) bir dosya üzerinde çalıştırır; veritabanına yazmaz, dosyayı
bir yere göndermez, kareleri geçici klasöre yazıp siler. `--json` yalnızca JSON yazar.

```bash
docker compose run --rm --no-deps -v "<video klasörü>:/media:ro" worker \
  python -m app.scripts.measure_media /media/ders.mp4 --language tr
```

Ölçüm ortamı (2026-11-22): Windows + Docker Desktop, 20 CPU, 15,5 GB; `TRANSCRIPTION_MODEL=tiny`, `multilingual-e5-base`,
Tesseract 5.5.0. Örnek medya: 1080p/25 fps sentetik İngilizce ders (7 slayt: formül, kod, diyagram, tablo; anlatım Windows
konuşma sentezi), 11 dakika; 1 ve 2 saatlik sürümler aynı dersin arka arkaya eklenmesiyle. Onaylı gerçek ders kaydı
henüz yok; sayılar gerçek kayıtla yeniden ölçülmeli (özellikle konuşmacı sesi ve yoğun slaytlar).

| Medya | Transkripsiyon | Kare çıkarma | OCR (kare başına) | Toplam iş | Süreye oranı | En yüksek bellek |
|---|---|---|---|---|---|---|
| 11 dk, 11,7 MB, 35 slayt | 29 sn (148 segment) | 20 sn (35 kare, 1,4 MB) | 37 sn (1,05 sn) | 91 sn | 0,14 | 1,9 GB |
| 1 sa, 71,5 MB, 210 slayt | 110 sn (905 segment) | 71 sn (210 kare, 8,6 MB) | 217 sn (1,03 sn) | 424 sn | 0,11 | 5,1 GB |
| 2 sa (yalnızca transkripsiyon) | 223 sn (1845 segment) | — | — | — | — | 7,8 GB |

- Embedding modelinin yüklenmesi ~9 sn ve ~1,1 GB; çalıştırıcıda bir kez olur.
- Transkripsiyonun kendi belleği: 11 dk 0,9 GB, 1 sa 4,1 GB, 2 sa 7,8 GB (≈ 3,7 GB/saat). Ses çözme + VAD bunun
  ~1 GB'ı (1 saatte); geri kalanı faster-whisper'ın tüm sesin özelliklerini birden hesaplaması.
- Uçtan uca (gerçek iş kuyruğu, test veritabanı): 11 dk'lık ders 28 sn'de `ready` (transkript), kareler 49 sn sonra;
  1 saatlik ders 130 sn'de `ready`, kareler 306 sn sonra. Kareler gelene kadar doküman kullanılabilir.
- Disk: kare başına ~41 KB PNG (1 saat ≈ 9 MB); medya iş bitince silinir, kalıcı olan transkript ve kareler.
- OCR süresi slayt sayısıyla, transkripsiyon süresi medya süresiyle büyür. Slaytı sık değişen ders (örn. 1 dakikada
  bir) için kare işi transkripsiyondan uzun sürer; video başına 300 kare sınırı OCR'ı ~5 dakikayla sınırlar.

## İş durumları

İş türleri (`processing_jobs.kind`, ADR-11): `transcription`, `frames` (slayt kareleri + OCR; yüklenen videoda
transkripsiyondan sonra, altyazılı videoda medya eklenince) ve `frame_interpretation` (yalnızca `FRAME_INTERPRETER`
yapılandırılmışsa). Eğitmen bir dokümanın işlerini `GET /api/documents/{id}/jobs` ile görür, birini
`POST /api/documents/{id}/jobs/{job_id}/cancel` ile iptal eder. Kare işlerinin hatası ya da iptali dokümanı bozmaz.

Doküman: `processing → ready | failed`. İş (`processing_jobs.status`):

| Durum | Anlamı |
|---|---|
| `queued` | Yüklendi, çalıştırıcıyı bekliyor. Medya `data/uploads/<ders>/<doküman>.<uzantı>` |
| `running` | Bir çalıştırıcı çalıştırıyor; `heartbeat_at` en çok 15 sn eski olmalı |
| `succeeded` | Transkript `<doküman>.vtt` olarak yazıldı (kare işi varsa medya ona kaldı), ya da kareler/betimlemeler yazıldı |
| `failed` | Kalıcı hata ya da deneme hakkı bitti; `error` nedeni yazar, doküman `failed`, dosyalar silindi |
| `cancelled` | Eğitmen iptal etti; doküman `failed`, dosyalar silindi |

Bakmak için:

```bash
docker compose exec db psql -U learning learning_assistant -c "SELECT id, document_id, status, attempts, error, heartbeat_at FROM processing_jobs ORDER BY id DESC LIMIT 20"
```

## Saklama ve temizlik (#25)

- Yüklenen medya, onu okuyan son iş (transkripsiyon ya da kare işi) bitince silinir; başarısızlık ve iptal dahil.
- Kare görüntüleri dokümanla yaşar. Gizli bir içerik yakalanmış tek kare `DELETE /api/documents/{id}/frames/{frame_id}`
  ile silinir.
- `worker` her `STORAGE_SWEEP_INTERVAL_S` (1 saat; 0 = kapalı) sahipsiz dosyaları siler: dokümanı olmayan
  `data/uploads/<ders>/<id>[.frames].<uzantı>` ve `frames/<id>` klasörleri, kare işi sürmeyen `frames/<id>.partial` ve
  `frames/<id>.previous`, hiçbir etkin işin girdisi olmayan ara medya. `STORAGE_ORPHAN_GRACE_S`'ten (1 saat) yeni
  dosyalara dokunulmaz. Silinenlerin sayısı günlüğe yazılır ("Depolama temizliği: … silindi"). Sembolik bağlantılar
  izlenmez; `data/uploads` dışına çıkan yol silinmez. Her silme, dokümanın satırı kilitlenip etkin işler yeniden
  okunduktan sonra yapılır; o an kilitli doküman bir sonraki tura kalır.

## Kurtarma

- **`worker` ya da `api` yeniden başladı, iş yarıda kaldı.** Bir şey yapmak gerekmez. Medya diskte kaldığı için iş
  120 sn sonra yeniden kuyruğa alınır ve baştan çalışır. İkinci deneme de yarıda kalırsa doküman "İşlem yarıda kaldı"
  ile `failed` olur; eğitmen dosyayı yeniden yükler.
- **Doküman uzun süre "İşleniyor".** Önce `worker`'ın çalıştığını ve günlüğünü kontrol edin
  (`docker compose logs worker`). `queued` bekleyen iş varsa ve çalıştırıcı yoksa `docker compose up -d worker`.
  İşi durdurmak için `POST /api/documents/{id}/cancel` ile iptal edin (arayüzde düğme henüz yok).
  Gerçek `worker` süreciyle denendi (#31, `SIGKILL`): transkripsiyonun ortasında öldürülen iş yeniden başlatınca 2.
  denemede bitti; kare işinin ortasında öldürülen işte doküman `ready` kaldı (transkript kullanılabilir), yarım
  `frames/<id>.partial` klasörü ve medya diskte bekledi, iş 2. denemede bitti ve ikisi de silindi. İki durumda da tüm
  kareler geldi, kopya kare oluşmadı.
- **`worker` bellek yüzünden öldü** (uzun video; `docker compose ps` ile `worker` yeniden başlamış, `docker compose logs
  worker` ya da `dmesg`'de "Killed"/OOM). Yukarıdaki gibi yeniden denenir; ikinci denemede de ölürse doküman `failed`.
  Kalıcı çözüm: `worker`'a daha çok bellek ya da daha kısa `MAX_MEDIA_DURATION_S` ("Sınırlar"daki hesap).
- **Kareler gelmiyor ya da hepsi okunamıyor.** `docker compose exec worker tesseract --list-langs` `eng` ve `tur`
  göstermeli. Göstermiyorsa imaj Tesseract eklenmeden önce kurulmuştur: `docker compose up -d --build`. (Tesseract
  yokken kare adımı günlüğe uyarı yazıp kareleri atlar; doküman yine `ready` olur, bu yüzden hata kendini göstermez.)
  Kare işi başarısız olduysa medya silinmiştir; kareler için videoyu `POST /api/documents/{id}/frames` ile yeniden
  ekleyin.
- **Bir karede gizli içerik yakalandı** (öğrenci listesi, açık pencere). `DELETE /api/documents/{id}/frames/{frame_id}`;
  görüntü ve kayıt hemen silinir, eski adres ve alıntı 404 olur.
- **Veritabanı bağlantısı koptu.** Çalıştırıcı hatayı günlüğe yazar ve yoklamaya devam eder. Bağlantı gelince süren iş
  canlılık yazamadıysa yukarıdaki gibi yeniden denenir.
- **Disk doldu.** Medya parça parça yazılır. Yazma hatası yüklemeyi `5xx` ile bitirir; kayıt geri alınır ve yarım dosya
  silinir. Yer açıp yeniden yükleyin. Kalmış dosyaları çalıştırıcının temizliği bir saat içinde siler (yukarıda); elle
  de dokümanı olmayan `data/uploads/<ders>/<id>.*` dosyaları güvenle silinebilir.
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

Medya için ek denetim (#31), sırayla:

1. `docker compose ps`: `db` sağlıklı, `api` ve `worker` çalışıyor.
2. `docker compose exec worker tesseract --list-langs` → `eng`, `tur` (yoksa imaj eski: `docker compose up -d --build`).
3. `docker compose exec worker env | grep -E "TRANSCRIPTION_MODEL|FRAME_EXTRACTION|MAX_MEDIA_DURATION_S"`: kare
   isteniyorsa `FRAME_EXTRACTION=ocr`; süre sınırı `worker`'ın belleğine uygun ("Sınırlar").
4. Kısa bir video yükleyin: doküman `ready` olmalı, `GET /api/documents/{id}/jobs` iki işi (`transcription`, `frames`)
   `succeeded` göstermeli, `GET /api/documents/{id}/frames` kareleri vermeli, `data/uploads/<ders>/` altında medya
   (`<id>.mp4`) ve `frames/<id>.partial` kalmamalı.
5. İsteğe bağlı: `python -m app.scripts.measure_media` ile süre ve belleği bu makinede ölçün ("Kaynak kullanımı ve süre").

Durdurup yeniden başlatmak veri kaybettirmez: `docker compose restart worker` süren işi ~2 dakika sonra yeniden
dener. `docker compose down -v` ise veritabanını siler; yüklenen dosyalar (`data/uploads`) hacim değil klasör olduğu
için kalır ve sahipsiz kalır: temiz başlangıçta onu da elle boşaltın.

## Gizlilik ve ders izolasyonu (#31)

Doğrulanan kurallar (`backend/tests/test_media_isolation.py`; tek tek durumlar `test_frames_db.py`,
`test_visual_media.py`, `test_access.py`):

- Her medya/kare ucu (kare listesi, kare görüntüsü, dosya, parçalar, `frame:` alıntısı, iş listesi ve iptali, kare
  silme, kare videosu ekleme, yorumlama, işlem iptali, doküman silme) yedi rolle denenir. Oturumsuz `401`; ders dışı,
  başka dersin eğitmeni ve üyeliği kaldırılmış kullanıcı `404` (varlık sızdırılmaz); öğrenci ve TA okur, yönetemez
  (`403`); yetkisiz istek hiçbir şeyi değiştirmez. Üyelik kaldırılınca açık oturum da erişimi hemen kaybeder.
- Onaysız, işlenen ya da başarısız videonun kareleri, görüntüsü, dosyası ve alıntısı yalnızca eğitmene görünür; soruda
  bağlam olamaz ve aramaya girmez.
- Başka dersin videosu ya da karesi soruda bağlam olamaz (`422`); bir dokümanın yolu üzerinden başka dokümanın karesi,
  işi ya da görüntüsü bulunmaz; aynı medya iki derste yüklenirse kareler ve dosyalar ayrı kalır.
- Video yenilenince ya da silinince eski kare kimlikleri, görüntü adresleri ve alıntılar `404`, istekteki eski kare
  `422`; soru kaydında yalnızca kimlik ve zaman kalır (görüntü, OCR metni ya da yol yok).
- Her adımdan sonra diskte tam olarak veritabanının bildiği dosyalar vardır (doküman dosyası, etkin işin medyası, kare
  görüntüleri); temizlik tutarlı depoda hiçbir şey silmez.
- Bir iş iki çalıştırıcıya verilmez (`SKIP LOCKED`); çalıştırıcı yeniden dönünce kare ya da iş çoğalmaz.

Sınırlar: kare görüntüleri şifrelenmeden diskte durur (sunucu diskine erişen herkes görür); görüntüler
`Cache-Control: private, no-cache` ile sunulur ama tarayıcı önbelleğinden silinmesi garanti edilmez; soru kaydındaki
kare kimliği kare silinince boşa düşer (bilerek, ADR-11).
