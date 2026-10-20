# Interactive Learning Assistant

Ders materyaline dayalı (course-grounded) bir RAG çalışma asistanı. Planlanan dört yetenek:
- **kaynaklı soru-cevap**: sayfa / video-zaman alıntısıyla; kanıt yoksa reddeder
- **pratik soru üretimi**
- **rubrikle cevap değerlendirme**
- **ölçülen hallucination oranı**

Engineering Design II · Project 8. Pilot ders: Veri Yapıları ve Algoritmalar.

> **Durum — Sprint 1 tamam:** PDF yükleyip içinden kaynaklı soru sorulabiliyor.
> - **Ders oluşturma** ve dersler arası tam izolasyon.
> - **Materyal yükleme hattı:** PDF/PPTX okuma → temizleme → sayfa numaralı parçalama → multilingual-e5 ile vektörleştirme (pgvector). Her yüklemede adım adım rapor.
> - **Hibrit RAG arama:** anlamsal (e5 + pgvector) ve kelime (PostgreSQL tam metin) aramaları RRF ile birleşir. Alakasız sorular modele hiç gitmeden elenir.
> - **AI chat:** OpenRouter üzerinden Claude; cevap akarak gelir, her bilgi [1], [2] ile kaynağına bağlanır, kaynak yetmezse reddeder. Takip sorularını hatırlar.
> - **Kaynak gösterme:** alıntıya tıklayınca PDF'in gerçek sayfası açılır, alıntılanan satırlar işaretlenir. "Nasıl bulundu" paneli arama skorlarını gösterir.
> - **Eğitmen etkinliği:** dersin soru-cevap özeti (sayılar, son 14 gün, en çok alıntılanan kaynaklar, materyalde cevabı bulunamayan sorular) kayıtlı mesajlardan hesaplanır.
> - **Henüz yok:** video, pratik, değerlendirme, sık hatalar ve eğitmen onayı, hallucination ölçümü, arayüzde gerçek giriş (#12). Backend'de kimlik ve ders düzeyinde yetki var (#11): her istek oturum çerezi ve ders üyeliği ister; arayüzdeki giriş hâlâ sahte olduğu için #12 gelene kadar arayüz backend'e oturumsuz istek atar ve `401` alır. Pratik, sık hatalar, öğrenme kaydı ve rubrik endpoint'leri yetki denetiminden sonra `501` döner.
>
> Hangi özelliğin hangi dosyada olduğu ve durumu: [ANALYSIS.md §14.1](docs/ANALYSIS.md).
> Kapsam, gereksinimler, mimari ve yol haritası: **[docs/ANALYSIS.md](docs/ANALYSIS.md)**

## Klasör yapısı

```
Learning-Asistent/
├── backend/               FastAPI uygulaması
│   ├── app/
│   │   ├── api/           HTTP endpoint'leri (pratik, eğitmen, öğrenme kaydı, rubrik: şimdilik 501)
│   │   ├── schemas/       API sözleşmeleri (Pydantic)
│   │   ├── core/          yapılandırma
│   │   ├── db/            bağlantı, oturum, ORM modelleri
│   │   ├── ingestion/     parser'lar, temizleme, chunking, transkript
│   │   ├── retrieval/     dense + lexical + RRF + rerank + video-zaman
│   │   ├── generation/    answer · question · grade
│   │   ├── verification/  kaynak ID, pratik kontrolleri, iddia / judge, hallucination
│   │   ├── routing/       task router
│   │   ├── llm/           model gateway (local / hosted)
│   │   ├── courses/       ders listesi
│   │   ├── sources/       alıntılanan kaynağı getirme
│   │   ├── auth/          ders bazlı erişim kontrolü (henüz iskelet)
│   │   ├── learning/      öğrenme kaydı
│   │   └── instructor/    sık hatalar, onay / düzeltme, rubrikler
│   ├── migrations/        Alembic
│   └── tests/
├── frontend/src/
│   ├── ui/                tasarım sistemi bileşenleri (docs/UI_GOREVLERI.md)
│   ├── layouts/           sidebar + topbar iskeleti, giriş düzeni
│   ├── services/          veri katmanı (gerçek API; kimlik doğrulama hâlâ mock)
│   ├── mock/              yalnızca kimlik doğrulama (backend yok; #12)
│   ├── features/          tutor/, materials/, courses/
│   └── pages/             route başına sayfa (auth, instructor, student)
├── evaluation/            gold set'ler, rubrikler, insan etiketleri, harness/
├── docs/                  analiz, ekip kararları (DECISIONS), sözleşmeler (CONTRACTS)
├── docker/                PostgreSQL init
├── .github/               CI, issue / PR şablonları
└── docker-compose.yml
```

## Hızlı başlangıç

### Docker ile

```bash
cp .env.example .env
docker compose up --build
```

- Web: <http://localhost:5173>
- API: <http://localhost:8000/health> (dokümantasyon: <http://localhost:8000/docs>)
- PostgreSQL + pgvector: `localhost:5432`

API açılırken veritabanı şemasını günceller ve demo dersini (BLM2512) oluşturur.
Portlar doluysa `.env` içindeki `WEB_PORT`, `API_PORT`, `POSTGRES_PORT` değiştirilebilir.

İlk açılışta API embedding modelini (multilingual-e5-base, ~1 GB) indirir; birkaç dakika sürebilir.
Sonraki açılışlarda model `models` volume'undan yüklenir, internet gerekmez.

### Hesaplar (DECISIONS.md ADR-1, 2, 4)
- Öğrenci kendi hesabını açar (`POST /auth/register`), derse eğitmenin verdiği **katılım koduyla** katılır.
- Eğitmen rolü kayıtla alınamaz. Eğitmen hesabı sunucuda açılır:
  `docker compose exec api python -m app.scripts.create_instructor --email ... --name "..."` (şifre sorulur).
  Bu hesabın açtığı dersin eğitmeni olur; katılım kodunu `GET /courses/{id}/join-code` verir. Hesaplardan önce
  açılmış dersler (ör. BLM2512) eğitmensizdir: `--course BLM2512` hesabı o dersin eğitmeni yapar.
- Geliştirme hesapları yalnızca `.env`'de `SEED_DEV_ACCOUNTS=true` ve `DEV_INSTRUCTOR_PASSWORD` /
  `DEV_STUDENT_PASSWORD` verilmişse açılış betiğiyle oluşturulur (demo dersin eğitmeni ve öğrencisi). Üretimde kapalıdır.
- Soru sormadan önce aydınlatma metni onaylanır (`PUT /me/consent`); araştırma kaydı ayrı ve varsayılan kapalıdır.
  Eğitmen etkinliği yalnızca araştırma kaydını açan öğrencilerden, toplu hesaplanır; 3 öğrenciden az veri varsa boş döner. `DELETE /me/data` sohbetleri,
  `DELETE /me` hesabı siler.

### Demo
Giriş gerçektir (e-posta + şifre, sunucu oturumu). `docker compose up` ile açılan yerel sistemde **demo
hesapları kendiliğinden gelir**; giriş ekranının altındaki **Demo hesapları**'na tıklayınca şifresiz girilir:

- **Dr. Ayşe Demir** (eğitmen): demo dersin (BLM2512) ve içeri alınan OCW derslerinin eğitmeni
- **Elif Kaya** (öğrenci): BLM2512'ye kayıtlı; diğer derslere katılım koduyla katılır

Derslerin **katılım kodları** da giriş ekranında listelenir; öğrencinin "Derse katıl" kutusunun altında tek tıkla
yazılır. İlk girişte aydınlatma metni onaylanır.

> Bu sunum modu yalnızca yerel geliştirme içindir (`docker-compose.yml` varsayılanı; uygulamanın kendi
> varsayılanı kapalı). Gerçek kurulumda `SEED_DEV_ACCOUNTS=false` ve `DEMO_LOGIN=false` olmalı.
> Gerçek eğitmen hesabı: `docker compose exec api python -m app.scripts.create_instructor --email ... --name "..." --course BLM2512`.

**MIT 6.006 dersini eklemek (isteğe bağlı, sunum için):**
1. [6.006 Introduction to Algorithms](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/download/) sayfasından paketi indirip açın.
   Klasörü `data/ocw/6-006-spring-2020` olarak koyun (içinde `data.json` olmalı). `data/` git'e girmez.
2. `docker compose exec api python -m app.scripts.import_ocw /code/data/ocw/6-006-spring-2020`
   (89 PDF; ilk seferde ~15 dk). Ders demo eğitmenine otomatik bağlanır; kodu giriş ekranında görünür.

1. Eğitmen olarak gir. Ders genel bakışında **katılım kodunu** gör; yeni ders için **+ Ders oluştur**.
2. Dersin **Materyal yönetimi** sekmesinde beyanı işaretle ve PDF sürükle. Yükleme sonrası dokümana tıklayınca, yükleme raporu (okunan sayfa, temizlenen satırlar, parça ve vektör sayısı) ve sistemin çıkardığı parçalar sayfa numaralarıyla görünür.
3. Öğrenci olarak gir (ya da **Hesap oluştur**), Derslerim'de katılım koduyla derse katıl, dersin **AI Tutor**'unu aç ve bir soru sor (ör. *Binary search'te neden sağ yarıyı atabiliyoruz?*). Cevap akarak gelir; sarı numaraya ya da kaynak kartına tıklayınca sağda PDF'in o sayfası açılır ve alıntılanan satırlar işaretlenir.
4. Takip sorusu sor (ör. *Peki karmaşıklığı ne?*). Asistan önceki soruyu hatırlar.
5. Ders dışı bir soru sor (ör. *Fransa'nın başkenti neresi?*). Asistan "materyalde yok" der; "Nasıl bulundu" panelinde benzerliğin eşiğin altında kaldığı görülür.

Arayüzün tasarım kuralları ve ekibe kalan ekranlar: **[docs/UI_GOREVLERI.md](docs/UI_GOREVLERI.md)**.

### LLM
`.env` dosyasında:

```
LLM_PROVIDER=openrouter
LLM_API_KEY=<OpenRouter anahtarı>
LLM_MODEL=anthropic/claude-opus-5.5
```

- Anahtar **yalnızca `.env`** dosyasına yazılır, asla commit'lenmez.
- `LLM_MODEL` ile model değiştirilebilir. Örneğin `anthropic/claude-haiku-5.5` çok daha ucuzdur.
- Anahtar boşsa sistem **LLM'siz** çalışır: cevap yerine en ilgili ders parçasını kaynağıyla gösterir.

### Transkripsiyonu açmak (isteğe bağlı)

Altyazısı (.vtt) olmayan ders videosu/sesi (.mp4 .webm .mkv .mov .mp3 .m4a .wav, en çok 2 GB) yerelde yazıya çevrilebilir
(faster-whisper, CPU; ses dışarı gönderilmez, DECISIONS.md ADR-6). Varsayılan **kapalıdır**; kapalıyken medya yüklemesi
reddedilir ve altyazı istenir. Açmak için `.env`:

```
TRANSCRIPTION_MODEL=large-v3-turbo
```

Sonra `docker compose up --build`. Model ilk açılışta indirilir (~1,6 GB), sonra internetsiz çalışır. CPU'da 1 saatlik bir
ders dakikalar sürer; yükleme hemen döner, doküman "İşleniyor" görünür ve bitince "İndekslendi" olur (liste kendiliğinden
yenilenir). Süren iş sunucu yeniden başlarsa (ör. `--reload`) "Başarısız" olur; dosyayı yeniden yükleyin. Hızlı deneme için
`TRANSCRIPTION_MODEL=tiny` (düşük doğruluk).

### Cevap akışı ve alıntı doğrulama
`POST /api/ask/stream` sırasıyla şu olayları gönderir:
1. `retrieval`: bulunan parçalar
2. `delta`: **taslak** metin parçaları
3. `done`: doğrulanmış cevap

Hata olursa `error` olayı gelir.

- **Taslak doğrulanmamıştır.** Arayüz onu soluk renkte, "Kaynaklarla kontrol ediliyor…" notuyla ve alıntıları tıklanamaz halde gösterir. `done` geldiğinde taslak tamamen `done.answer` ile değiştirilir.
- **Doğrulama** (`backend/app/verification/citations.py`) cümle düzeyinde çalışır:
  - Uydurma etiketli (`[S9]`) ya da hiç alıntısı olmayan iddia cümleleri cevaptan çıkarılır.
  - Etiketsiz cümleler, aynı paragrafta kendilerinden sonra gelen etiketli cümlenin kaynağını paylaşır.
  - Desteklenen iddia oranı %60'ın altına düşerse ya da geçerli alıntı kalmazsa cevap gösterilmez.
- **`done.outcome`** sonucu bildirir:
  - `answered`: cevaplandı
  - `insufficient_evidence`: materyalde yok
  - `unsupported`: doğrulamadan geçemedi
  - `model_refusal`: model reddetti
  - `provider_failure`: modele ulaşılamadı; en ilgili parça alıntılandı

  `unsupported_removed` kaç cümlenin çıkarıldığını söyler.
- **Gecikme:**
  - İlk taslak kelimeler, aramadan sonra modelin ilk token süresi kadar gecikir (canlı ölçüm #8 baseline'ında yapılacak).
  - Doğrulama yerel ve milisaniyeler sürer; `done`, model yazmayı bitirir bitirmez gelir.
  - Alakasız sorular LLM'e hiç gitmez; anında `insufficient_evidence` döner.

### Yerel geliştirme

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,embeddings]"   # embeddings: torch + sentence-transformers
alembic upgrade head        # PostgreSQL çalışıyor olmalı
python -m app.scripts.seed_demo
uvicorn app.main:app --reload
pytest
```

Testler modeli indirmez; sahte bir embedder kullanır. Veritabanı gerektiren testler yalnızca `TEST_DATABASE_URL` tanımlıysa çalışır, yoksa atlanır (CI'da tanımlı).
Bu veritabanının tabloları her testte boşaltılır, o yüzden ayrı bir test veritabanı kullanın:

```bash
docker compose exec db createdb -U learning learning_assistant_test
```

```bash
TEST_DATABASE_URL=postgresql+psycopg://learning:learning@localhost:5432/learning_assistant_test pytest
```

Frontend (Node ≥ 20.19):

```bash
cd frontend
npm install
npm run dev
```

## Çalışma kuralları

- `main` korumalı. `feature/*` dallarından PR açılır; 1 review ve yeşil CI gerekir.
- **Ders materyalleri repoya commit'lenmez.** `data/` gitignore'dadır. Repoda yalnızca şemalar, scriptler ve anonim değerlendirme verisi bulunur.
- Hallucination vakaları Bug Tracker'a "Bug" şablonuyla girilir.
- GitHub Projects: Iterative Development (2 haftalık sprintler), Kanban, Bug Tracker.

## Ekip

Berke Akçay · Emir Ulaş Özdağ · Ceyda Yıldız · Nisanur İlhan · Mehmet Akif Kurt
