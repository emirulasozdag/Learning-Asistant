# Interactive Learning Assistant

Ders materyaline dayalı (course-grounded) bir RAG çalışma asistanı. Planlanan dört yetenek:
- **kaynaklı soru-cevap**: sayfa / video-zaman alıntısıyla; kanıt yoksa reddeder
- **pratik soru üretimi**
- **rubrikle cevap değerlendirme**
- **ölçülen hallucination oranı**

Engineering Design II · Project 8. Pilot ders: Veri Yapıları ve Algoritmalar.

> **Durum:** Proje iskeleti. Her fonksiyonel özelliğin dosyası, imzası ve endpoint'i var, ama hiçbirinin mantığı henüz uygulanmadı.
> Fonksiyonlar `NotImplementedError` fırlatır, endpoint'ler `501` döner. Hangi özelliğin hangi dosyada olduğu: [ANALYSIS.md §14.1](docs/ANALYSIS.md).
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
│   ├── api/               tipler + istemci
│   ├── features/          courses, video, qa, sources, practice, feedback, learning, instructor
│   └── pages/             öğrenci ve eğitmen sayfaları
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

- API: <http://localhost:8000/health> (dokümantasyon: <http://localhost:8000/docs>)
- Web: <http://localhost:5173>
- PostgreSQL + pgvector: `localhost:5432`

### Yerel geliştirme

Backend (Python 3.12):

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head        # PostgreSQL çalışıyor olmalı
uvicorn app.main:app --reload
pytest
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
