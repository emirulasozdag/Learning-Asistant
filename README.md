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
> - **Henüz yok:** video, pratik, değerlendirme, eğitmen analizleri, hallucination ölçümü, giriş/yetki. Bu endpoint'ler `501` döner.
>
> Hangi özelliğin hangi dosyada olduğu ve durumu: [ANALYSIS.md §14.1](docs/ANALYSIS.md).
> Kapsam, gereksinimler, mimari ve yol haritası: **[docs/ANALYSIS.md](docs/ANALYSIS.md)**

## Klasör yapısı

```
Learning-Asistent/
├── backend/               FastAPI uygulaması
│   ├── app/
│   │   ├── api/           HTTP endpoint'leri (/health dışındakiler şimdilik 501)
│   │   ├── schemas/       API sözleşmeleri (Pydantic)
│   │   ├── core/          yapılandırma
│   │   ├── db/            bağlantı, oturum, ORM tabanı (tablolar WP3)
│   │   ├── ingestion/     parser'lar, temizleme, chunking, transkript
│   │   ├── retrieval/     dense + lexical + RRF + rerank + video-zaman
│   │   ├── generation/    answer · question · grade · conversation
│   │   ├── verification/  kaynak ID, pratik kontrolleri, iddia / judge, hallucination
│   │   ├── routing/       task router
│   │   ├── llm/           model gateway (local / hosted)
│   │   ├── courses/       ders listesi
│   │   ├── sources/       alıntılanan kaynağı getirme
│   │   ├── auth/          ders bazlı erişim kontrolü
│   │   ├── learning/      öğrenme kaydı
│   │   └── instructor/    sık hatalar, onay / düzeltme, rubrikler
│   ├── migrations/        Alembic
│   └── tests/
├── frontend/src/
│   ├── ui/                tasarım sistemi bileşenleri (docs/UI_GOREVLERI.md)
│   ├── layouts/           sidebar + topbar iskeleti, giriş düzeni
│   ├── services/          veri katmanı (gerçek API + mock)
│   ├── mock/              henüz backend'i olmayan alanlar için örnek veri
│   ├── features/          tutor/, materials/, courses/
│   └── pages/             route başına sayfa (auth, instructor, student)
├── evaluation/            gold set'ler, rubrikler, insan etiketleri, harness/
├── docs/                  analiz, ekip belgeleri
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

### Demo
Giriş ekranındaki **demo hesaplarıyla** tek tıkla girilir (kimlik doğrulama backend'i henüz yok; oturum tarayıcıda tutulur):
**Dr. Ayşe Demir** (eğitmen) ve **Elif Kaya** (öğrenci).

1. Eğitmen olarak gir. Sol menüdeki **+** ile bir ders oluştur (ya da hazır BLM2512'yi kullan).
2. Dersin **Materyaller** sekmesine PDF sürükle. Yükleme sonrası dokümana tıklayınca, yükleme raporu (okunan sayfa, temizlenen satırlar, parça ve vektör sayısı) ve sistemin çıkardığı parçalar sayfa numaralarıyla görünür.
3. Öğrenci olarak gir, dersin **AI Tutor**'unu aç ve bir soru sor (ör. *Binary search'te neden sağ yarıyı atabiliyoruz?*). Cevap akarak gelir; sarı numaraya ya da kaynak kartına tıklayınca sağda PDF'in o sayfası açılır ve alıntılanan satırlar işaretlenir.
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
