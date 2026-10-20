# Ortak sözleşmeler ve ortak dosya protokolü

> Issue #6 — *[S01-C] Agree SRS, shared contracts and identity/consent decisions*.
> Bu doküman ekibin kabul ettiği (DECISIONS.md, 2026-10-20) sözleşmeleri **dondurur**.
> Kod: `backend/app/schemas/` (Pydantic) ve `frontend/src/api/types.ts` (TypeScript).
> Kararlar: [DECISIONS.md](DECISIONS.md).

## 0. Nasıl okunur

İki aşamalı yol:

- **PR A** (#67, merge edildi): yalnızca dokümanlar; hiçbir kod dosyası değişmedi.
- **PR B** (#6'yı kapatan PR): doküman düzeltmeleri ve kabul edilen sözleşmelerin **yalnızca tip tanımları**
  (`schemas/` + `types.ts`). Endpoint, servis, ORM, migration veya iş mantığı yoktur; çalışma zamanı davranışı
  değişmez, yeni tipleri kullanan bir router bulunmaz.

Her sözleşmenin **Durum** satırı iki değerden birini (veya iki parçaya bölünmüşse her parça için birini) alır:

- **Bu PR'da tip olarak donduruldu.** Tip tanımı PR B ile koda girdi; kullanan endpoint/servis ilgili işte yazılır.
- **Metin donduruldu; koda geçişi #…** Alan adları ve tipler bu dokümanda kesinleşti; koda geçişi (üreten kod
  değişmeden tip eklenemediği için) belirtilen işin sahibine bırakıldı.

Her bölümde "Koddan farklar" listesi vardır. Etiketler: **[ekleme]** geriye uyumlu alan ekleme,
**[KIRICI]** mevcut alanı/tipi/davranışı değiştirir.

Kural (bütün sözleşmeler için): iki taraf aynı alan adlarını kullanır (`snake_case`); Pydantic `Literal`/`StrEnum`
değerleri TypeScript birleşim tipleriyle birebir aynıdır; kullanıcıya gösterilen Türkçe metin API değerinde değil
arayüz katmanında (`labels.ts`) üretilir.

---

## 1. Kaynak (evidence) referansı

**Durum:** Metin donduruldu; koda geçişi evidence işi / #16 (pratik üretimi). Bu PR'da yalnızca TS
`SourceDetail.material_type` tipi düzeltildi (aşağıda).

**Şu an.**

| | Backend | Frontend |
|---|---|---|
| `Citation` | `source_id, document_title?, page?, t_start?, t_end?` | aynı |
| `RetrievalHit` | `source_id, document_title, page, dense_score, lexical_rank, used` (**`t_start/t_end` yok**) | aynı |
| `SourceDetail.material_type` | `MaterialType` | `MaterialType` (PR B'de `string`'den düzeltildi) |
| `SourceUsage` (PR #68, etkinlik) | `source_id, document_title, page, citations` | satır içi tip; `Citation` ile ilişkisi yok |

`source_id`, bir `Chunk`'ın kimliğinin metin hali; alıntıların tek kimliği.

**Önerilen sözleşme.**

```
Citation {
  source_id:      str            # opak; frontend içeriğini yorumlamaz
  document_id:    int
  document_title: str
  material_type:  MaterialType
  page:           int | null     # PDF/PPTX
  t_start:        float | null   # saniye, videonun başından
  t_end:          float | null
}

RetrievalHit = Citation + { dense_score: float | null, lexical_rank: int | null, used: bool }

SourceDetail  (mevcut alanlar) + { course_id: int }     # TS: material_type: MaterialType
```

Değişmezler:
- `answer` içindeki `[n]`, `citations[n-1]`'e karşılık gelir.
- Bir `Citation` ya `page` ya da `t_start`/`t_end` taşır; ikisi birden boş olabilir (sayfasız metin), ikisi birden dolu olmaz.
- Doküman silinmişse `GET /sources/{source_id}` `404 {code: "source_not_found"}` döner; arayüz "kaynak artık yok" der.
- `SourceDetail.course_id`, erişim kontrolü içindir (§3).

**Koddan farklar.**
- `Citation.document_id`, `material_type` eklenir; `document_title` zorunlu olur — **[KIRICI]**. Tip tek başına
  eklenemez: `answer.to_citation` ([answer.py](../backend/app/generation/answer.py)) bu alanları doldurmazsa çalışma
  zamanında `ValidationError` oluşur ve `RetrievedPassage` `material_type` taşımadığı için arama katmanı da
  değişmelidir. **Metin donduruldu; koda geçişi evidence işi / #16.**
- `RetrievalHit`'e `document_id`, `material_type`, `t_start`, `t_end` eklenir — **[ekleme]**. Metin donduruldu; koda geçişi aynı iş.
- `SourceDetail.course_id` — **[ekleme]**. **#11'de koda geçti** ([lookup.py](../backend/app/sources/lookup.py)).
- TS `SourceDetail.material_type: string` → `MaterialType` — kırıcı değil (tüketici `materialLabel(type: string)`
  `MaterialType`'ı kabul eder). **Bu PR'da tip olarak donduruldu.**
- `SourceUsage` (PR #68) ileride `Citation + {citations: int}` olmalıdır; üretici ([instructor/activity.py](../backend/app/instructor/activity.py))
  değişeceği için bu PR'da yapılmadı.

---

## 2. Pratik ve geri bildirim

**Durum:** Bu PR'da tip olarak donduruldu (`schemas/practice.py`, `schemas/evaluation.py`, `types.ts`).
Denemenin *saklanması* (#15) ADR-4'teki `research_logging` onayına bağlıdır; üretim (#16) ve arayüz (#17) bu
tiplerden başlar.

**Şu an.**

| | Backend | Frontend |
|---|---|---|
| `PracticeRequest` | `course_id, type, topic?, source_id?` | aynı |
| `PracticeItem` | `id, type, prompt, options?, source: Citation` | aynı |
| `AnswerSubmission` | `answer_text, selected_option` (tam biri dolu; PR B'den önce: `answer: str`) | `AnswerSubmission` tipi; `api.submitAnswer(itemId, body: AnswerSubmission)` |
| `AnswerFeedback` | `attempt_id, item_id, score, max_score, understood, missing_concepts, explanation, citations, follow_up_item_id` | aynı |
| Pratik arayüzü | — | yok: `PracticePage` ve `mock/practice.ts` PR #68'de silindi; `/student/practice` artık `/student`'a yönleniyor ([router.tsx](../frontend/src/router.tsx)) |

**Uygulandı (ai-foundation, ADR-7):** `POST /practice` ve `POST /practice/{id}/answer` çalışır; AI Tutor'da
`generate_practice` aracıyla sohbetin içinde de soru gelir (§9). Kontrolden geçen soru yoksa `422 no_valid_item`;
soru yok, reddedilmiş ya da üye değilse `404 practice_item_not_found` **[ekleme]**; cevap türü uyuşmazsa `422`;
açık uçlu cevap değerlendirilemezse `503` (deneme kaydedilmez). `AnswerFeedback`'e **[ekleme]**: `correct_option`,
`reference_answer`, `criteria[{description, awarded, points, rationale}]` (yalnızca cevaptan sonra). Saklama:
`practice_questions` (aday + kontrol sonuçları + gizli anahtar), `practice_rubrics` (üretilen rubrik `origin=generated`,
onaysız), `practice_attempts` (`research_logged` cevap anındaki onay; analitik yalnızca bunları kullanır).
Kaynak politikası: not verilen ödevler (`material_type=assignment`, çözümleri dahil) pratik kaynağı olmaz
(`source_id` ile istenirse `422`); pratik problemleri ve yayımlanmış eski sınavlar kullanılır.

**Önerilen sözleşme.**

```
Difficulty = "easy" | "medium" | "hard"

PracticeRequest {
  course_id: int, type: PracticeType,
  topic?: str | null, source_id?: str | null,
  difficulty?: Difficulty | null,
  follow_up_of_attempt_id?: int | null          # "Bu eksik üzerine çalış"
}

PracticeItem {
  id: int, course_id: int, type: PracticeType,
  topic: str | null, difficulty: Difficulty,
  prompt: str,
  options: list[str] | null,                    # yalnızca mcq
  source: Citation
}
# Cevap anahtarı, referans cevap ve açıklama gönderimden ÖNCE hiçbir yanıtta dönmez.

AnswerSubmission {
  answer_text: str | null,                      # short_answer, code_tracing
  selected_option: int | null                   # mcq (options indeksi)
}                                               # türüne göre tam biri dolu

AnswerFeedback {
  attempt_id: int, item_id: int,
  score: float, max_score: float,               # formatif; resmî not değildir
  understood: list[str],
  missing_concepts: list[str],
  explanation: str,
  citations: list[Citation],
  follow_up_item_id: int | null
}
```

Hata davranışı: kontrolden geçen bir item üretilemezse `422 {code: "no_valid_item"}`; geçmeyen item hiçbir zaman döndürülmez (FR-12).
`difficulty` Türkçe etiketi (`Kolay/Orta/Zor`) arayüzde üretilir.

**Koddan farklar.**
- `PracticeRequest.difficulty`, `follow_up_of_attempt_id` — **[ekleme]**.
- `PracticeItem.course_id, topic, difficulty` — **[ekleme]**.
- `AnswerSubmission.answer` → `answer_text` / `selected_option` — **[KIRICI]**. Pydantic doğrulayıcısı "tam biri dolu"
  kuralını uygular; eski `{"answer": …}` gövdesi artık `422` döner. Bu PR'da etkilenen yerler:
  `backend/tests/test_api_skeleton.py` (gövde güncellendi) ve `api.submitAnswer` (imza `AnswerSubmission` aldı).
  Başka tüketici yok (endpoint `501`, pratik arayüzü silindi).
- `AnswerFeedback.attempt_id, item_id, understood` — `attempt_id` ve `item_id` zorunlu. Üreten kod yok (`501`), bu yüzden
  çalışma zamanında kırıcı değil; üretici (`generation/grade.py`, #16) bu alanları doldurmak zorundadır.
- `PracticeItem.course_id`, `difficulty` zorunlu (`topic` boş olabilir) — aynı şekilde üretici #16'dır.
- Frontend: `mock/practice.ts` PR #68'de silindi; #17 `types.ts` tiplerini kullanır.

---

## 3. Kullanıcı ve ders bağlamı

**Durum (ADR-1, ADR-2, ADR-4 kabul edildi):**
- **Bu PR'da tip olarak donduruldu:** `Role`, `UserOut`, `Membership`, `Consent`, `ConsentUpdate`, `Me`,
  `JoinCourseRequest`, `LoginRequest`, `RegisterRequest` (`schemas/common.py`, yeni `schemas/auth.py`, `types.ts`).
  Bu tipleri kullanan endpoint yoktur; #11 (backend) ve #12 (frontend) bunlardan başlar.
- **Metin donduruldu; koda geçişi #11:** `CourseSummary.role` zorunluluğu, `SourceDetail.course_id`, `GET /courses`
  davranışı, ORM/migration (`users`, `enrollments`, onay, `conversations.user_id`, `documents.approved_*`),
  hata kodlarının üretilmesi ve tüm endpoint'lerde yetki kontrolü.

**#11'de koda geçti (backend).** Aşağıdaki "Şu an" tablosunun backend sütunu #11 öncesini anlatır; frontend
sütunu #12'ye kadar geçerlidir.
- Endpoint'ler: `POST /auth/register|login|logout`, `GET /me`, `PUT /me/consent`, `POST /courses/join`; `GET /courses`
  yalnızca üye olunan dersler, `CourseSummary.role` zorunlu. Oturum: httpOnly `la_session` çerezi (SameSite=Lax),
  sunucuda yalnızca belirteç özeti; durum değiştiren istekte `Origin` başlığı izinli kökenlerden biri olmalı (CSRF).
- Yetki: §3 kuralları bütün ders kapsamlı endpoint'lerde uygulanır; 501 iskeletleri de önce yetki denetler.
  Yükleme, doküman silme, ders düzenleme, katılım kodu, rubrik girişi: `instructor`. Etkinlik, sık hatalar,
  rubrik listesi: `instructor | ta`. Okuma ve soru: dersin her üyesi.
- `Consent`: `consented_at == null` ⇔ aydınlatma metni kabul edilmedi (`policy_version` boş metin). `PUT /me/consent`
  yalnızca sunucunun güncel sürümünü (`PRIVACY_POLICY_VERSION`) kabul eder, değilse `422 validation_error`.
  Güncel sürüm kabul edilmeden `/ask`, `/ask/stream`, `/practice` → `403 consent_required`.
- Hata zarfı `{detail, code}` kimlik/yetki hatalarında ve bu PR'ın dokunduğu 404/409'larda üretilir; diğerleri
  (#5) hâlâ `{detail}`.
- **[ekleme] #11** (frontend #12 tüketir):
  - `GET /courses/{id}/join-code` → `JoinCode {code: str, expires_at: datetime | null}`; `POST` aynı yol → kodu yeniler
    (eski kod geçersiz, var olan üyelikler kalır). Yalnızca `instructor`.
  - `DELETE /me/data` → 204 (kullanıcının bütün sohbet ve mesajları); `DELETE /me` → 204 (hesap ve bağlı veri).
  - `ErrorCode`'a `consent_required`, `email_exists`.
  - `POST /courses/{id}/materials` formuna zorunlu `declaration=true` (ADR-3 beyanı) — **[KIRICI]** arayüz yükleme formu.
  - `POST /courses` yalnızca ders açma yetkisi olan hesap (eğitmen hesabı; seed ya da `create_instructor` betiği);
    değilse `403 insufficient_role`.
- **[ekleme] #12:** `UserOut.can_create_courses: bool` (ders açma yetkisi). Arayüz eğitmen alanını, ders açabilen
  ya da en az bir derste `instructor`/`ta` olan kullanıcıya açar; diğerleri öğrenci alanını görür (DECISIONS.md
  açık soru 7'deki öneri). Hiç dersi olmayan eğitmen de böylece eğitmen ana sayfasına gider.
- **[ekleme] Sunum modu (`DEMO_LOGIN`; uygulama varsayılanı `false`, yerel `docker-compose.yml` varsayılanı `true`):** `GET /auth/demo` → `DemoInfo {accounts, courses}`
  (geliştirme hesapları ve geliştirme eğitmeninin derslerinin katılım kodları); `POST /auth/demo-login {role}` →
  `Me` (şifresiz oturum). Hesap istemciden seçilmez, `DEV_*_EMAIL` ayarından okunur. Kapalıyken ikisi de düz 404.
  Yalnızca yerel demo içindir (ADR-1: üretimde demo hesap yok). Yerel compose demo hesaplarını da varsayılan açar
  (`SEED_DEV_ACCOUNTS`, Dr. Ayşe Demir / Elif Kaya); `import_ocw` içeri aldığı dersi demo eğitmenine bağlar.
- **#12'de koda geçti (frontend):** oturum `GET /me` ile çözülür (tarayıcıda kimlik saklanmaz); herhangi bir
  istekte 401 gelirse kullanıcı çıkış yapmış sayılır. Kayıt formunda rol seçimi yok. Aydınlatma metni ilk
  girişte gösterilir (`PRIVACY_POLICY_VERSION`, `services/authService.ts`, backend'deki değerle aynı olmalı).
  Öğrenci katılım koduyla derse katılır; eğitmen kodu ders genel bakışında görür ve yeniler. Yükleme ekranında
  ADR-3 beyanı işaretlenmeden dosya bırakılamaz.
- Şifre: 8–256 karakter; e-posta küçük harfe çevrilir ve basit biçim denetiminden geçer.

**Şu an.**

| | Backend | Frontend |
|---|---|---|
| Kullanıcı | `CurrentUser{id: int, roles: {course_id: Role}}` (iskelet) | `User{id: string, name, email, role: "student"\|"instructor", title?}` (localStorage, sahte; `services/authService.ts`) |
| Rol | `Role` = `student \| instructor \| ta` (`schemas/common.py`), ders başına | `types.ts`: `Role` (aynı üç değer). `authService.Role` hâlâ `student \| instructor`, global (#12) |
| `CourseSummary` | `CourseInfo` alanları (`instructor_name, term, level, department, description`, PR #68) + `role: Role \| None`, her zaman `null` | aynı |
| `GET /courses` | tüm dersler | tüm dersler |
| `PATCH /courses/{id}` | kimliksiz (PR #68) | `api.updateCourse` |
| Rol seçimi | — | kayıt formunda kullanıcı seçiyor |

**Dondurulan sözleşme.**

```
Role = "student" | "instructor" | "ta"

UserOut        { id: int, name: str, email: str, title: str | null, can_create_courses: bool }   # son alan: [ekleme] #12
Membership     { course_id: int, role: Role }
Consent        { research_logging: bool, consented_at: datetime | null, policy_version: str }
ConsentUpdate  { research_logging: bool, policy_version: str }
Me             { user: UserOut, memberships: list[Membership], consent: Consent }
JoinCourseRequest { code: str }                       # katılım kodu (ADR-2 A), ders kodu değildir
LoginRequest      { email: str, password: str }
RegisterRequest   { name: str, email: str, password: str }   # rol alanı YOK (ADR-1)

GET  /me                    → Me
POST /auth/login            → Me                      # LoginRequest;    oturum httpOnly çerezle kurulur
POST /auth/register         → Me                      # RegisterRequest; her zaman "student" kaydı
POST /auth/logout           → 204
PUT  /me/consent            → Consent                 # ConsentUpdate
GET  /courses               → list[CourseSummary]     # yalnızca üye olunan dersler; role zorunlu
POST /courses/join          → CourseSummary           # JoinCourseRequest
```

`CourseSummary.role: Role` (null olamaz). Bu PR'daki tip `Role | None` olarak kalır; zorunlu yapmak
`to_summary`'yi ([courses/service.py](../backend/app/courses/service.py)) değiştirmeyi gerektirir (#11).
Parola uzunluğu/karmaşıklığı kuralı ve `email` biçim doğrulaması bilerek tanımlanmadı; #11/#12 belirler
(bu PR'daki `LoginRequest`/`RegisterRequest` yalnızca alanları dondurur).
Login ve register bu dokümanda `Me` döndürür; ADR-1 bunu yalnızca "oturum çerezi" olarak belirtiyor, gövde
ayrıntısı #12 ile uygulamada doğrulanır.

Kurallar:
- Kimlik (kullanıcı kimliği, rol) hiçbir istek gövdesinde veya sorgu parametresinde gelmez; yalnızca oturumdan çözülür.
- Yetki ders düzeyinde kontrol edilir: ders kapsamlı her endpoint (`/courses/{id}/…`, `/ask`, `/practice`,
  `/instructor/…`) ve **kaynağın dersine bakan** endpoint'ler (`/sources/{id}`, `/documents/{id}/…`) üyelik ister.
- Hata kodları: `401 not_authenticated`; `403 insufficient_role` (üye ama rol yetersiz);
  `404` — üye olmayana dersin/dokümanın/sohbetin varlığı sızdırılmaz (`course_not_found`, `source_not_found`,
  `conversation_not_found`).
- `Conversation` ve `Message` kullanıcıya bağlanır; başka kullanıcının `conversation_id`'si `404` döner.
- Ana sayfa yönlendirmesi `memberships`'ten türetilir (kural: DECISIONS.md açık soru 7).
- Hosted modele kimlik bilgisi gönderilmez (ADR-5).

**Koddan farklar.**
- Yeni tipler (`Role`, `UserOut`, `Membership`, `Consent`, `ConsentUpdate`, `Me`, `JoinCourseRequest`, `LoginRequest`,
  `RegisterRequest`, `ErrorCode`, `ApiErrorBody`) — **[ekleme]**, bu PR'da tip olarak donduruldu; hiçbir endpoint kullanmaz.
- `Role`: backend'de `auth/dependencies.py` ve `schemas/courses.py` içindeki ayrı tanımlar `schemas/common.py`'deki tek
  tanıma bağlandı (yalnızca import; değerler aynı). Frontend'de `types.ts`'te `Role` eklendi; **ad çakışması:**
  `services/authService.ts` kendi `Role = "student" | "instructor"` tipini dışa aktarıyor. İki tip aynı dosyada
  içe aktarılmadığı sürece çakışmaz (bu PR'da hiçbir dosya `types.ts`'in `Role`'ünü kullanmıyor); #12 `authService`'i
  `types.ts` tiplerine taşır.
- `User.id: string → int`, `Role`'e `ta` — **[KIRICI]** (frontend `authService`, `RequireRole`, `homePath`). Metin donduruldu; koda geçişi **#12**.
- `CourseSummary.role` null olamaz — **[KIRICI]**. Metin donduruldu; koda geçişi **#11**.
- `GET /courses` davranışı: tümü → yalnızca üye olunanlar — **[KIRICI]** (davranış; mevcut demo ders için seed ile üyelik gerekir). **#11**.
- Kayıt formundan rol seçimi kalkar — **[KIRICI]** (arayüz). **#12**.
- Yeni tablolar (öneri; ayrıntıyı uygulayan PR netleştirir): `users`, `enrollments(user_id, course_id, role)`,
  onay kaydı; `conversations.user_id`; `documents.approved_by/approved_at` (ADR-3). **#11** (tek sahip, tek migration).
- `CourseInfo.instructor_name` (PR #68) serbest metin bir görüntü alanıdır; **yetki yalnızca `Enrollment`'tan gelir**
  (DECISIONS.md açık soru 8).

---

## 4. Video varlığı ve zaman

**Durum:** Tip (#14 PR a), davranış (#14 PR b+c) ve yerel transkripsiyon (#14 PR d) koda geçti: VTT yükleme, altyazısız
video/ses için arka plan transkripsiyonu ve oynatma konumu önceliği vardır.
**Yoktur:** `media_url` girme arayüzü (#19/#22), oynatıcı.
Videonun nerede barındırıldığı hâlâ bilinmiyor (DECISIONS.md açık soru 1); `media_url` bu yüzden barındırma
yönteminden bağımsız, opak bir URL'dir.

**Şu an.**
- `.vtt` yüklenebilir (`POST /courses/{id}/materials`); her zaman `material_type = "video"` kaydedilir. `material_type = "video"`
  ile `.vtt` ya da medya dışı dosya (ör. PDF) `422` ("Video türünde yalnızca altyazı (.vtt) ya da ders videosu/sesi
  yüklenir."). Medya dosyası için aşağıdaki "Transkripsiyon". Ayrıştırıcı
  `ingestion/parsers/vtt_parser.py` (yalnızca stdlib): zaman aralıkları, `<v Ad>` konuşmacı adı metne **girmez** (ADR-5),
  YouTube kayan satır tekrarı atılır, bozuk cue atlanıp `cues_skipped`e sayılır; dosya bütünüyle bozuksa ya da cue'ların
  %50'sinden fazlası atlandıysa `422`.
- Video dokümanı: `page_count = 0`, `duration_s` = en geç cue bitişi; parçalar `page = null`, `t_start/t_end` dolu
  (`chunk_timed_segments`: etkin embedder'ın gerçek token bütçesi, E5'te önek/özel token dahil 512;
  ardışık cue birleştirmede 60 sn tavanı). Tek başına token bütçesini aşan cue metin kaybetmeden bölünür;
  kelime zamanları bilinmediğinden her parça cue'nun özgün aralığını taşır (bu aralık 60 sn'yi aşabilir).
  `IngestionReport`: `pages_read = 0`, `empty_pages = 0`,
  `duration_s`, `cues_read`, `cues_skipped`; atlanan cue varsa `warnings`te Türkçe uyarı.
- `media_url` (isteğe bağlı form alanı): yalnızca `.vtt`/video yüklemesinde; yalnızca `https`, dolu ana makine, en çok 1000 karakter,
  değilse `422`. Değer opak saklanır ve `DocumentOut.media_url` ile video `SourceDetail.media_url` olarak aynen döner
  (`#t=` eklenmez; zamanı sarmak oynatıcının işidir). Verilmezse `null`.
- `AskRequest.video` verilirse: doküman var, aynı derse ait ve `material_type = "video"` olmalı, değilse
  `422` (Türkçe `detail`; hata zarfında `code` alanı **henüz yok**, bkz. §5). `time_s > duration_s` ise `duration_s`e kırpılır (hata değil).
- Öncelik: `retrieve(video=…)` o videonun `[time_s − video_window_s, time_s + video_window_s]` ile örtüşen parçalarını
  (`video_neighbors`, orta noktaya uzaklığa göre) RRF'e **ayrı bir sıralama** olarak `video_weight` ağırlığıyla ekler. Hiçbir
  parça elenmez; başka videoların aynı saniyesi öne çıkmaz. Alakasızlık kapısı (`relevant`, `best_similarity`,
  `keyword_coverage`, takip sorusu) videodan etkilenmez, yalnızca soru metninden hesaplanır.
- Frontend: `.vtt` yüklenir, alıntıda ve kaynak panelinde zaman ("Video, 12:34–13:20") görünür, `media_url` varsa "Videoda aç"
  bağlantısı çıkar; `video` isteği **göndermez** (oynatıcı yok).

**Transkripsiyon (altyazısı olmayan video/ses; ADR-6).**
- **Kapalı/açık.** `Settings.transcription_model` (`TRANSCRIPTION_MODEL`) boşsa **kapalı** (varsayılan): medya yüklemesi
  `422` ("Bu sunucuda transkripsiyon kapalı; videonun altyazısını (.vtt) yükleyin."), kayıt ve dosya kalmaz. Doluysa
  (ör. `large-v3-turbo`) medya kabul edilir. VTT/PDF/PPTX yolu bundan etkilenmez.
- **Kabul edilen medya:** `.mp4 .webm .mkv .mov .mp3 .m4a .wav` (sabit küme); sınır `Settings.max_media_bytes` = 2 GB
  (VTT/PDF/PPTX için 50 MB aynen). Medya belleğe okunmaz, diske parça parça kopyalanır; aşılırsa `422`, dosya kalmaz.
  Diğer uzantı `422`. Dil = `course.language` (otomatik algılama yok).
- **Durum makinesi.** Yükleme `201` döner: `status="processing"`, `chunk_count = 0`, `report = null`. Arka plan işi (kendi
  DB oturumu) bitince `ready` (zamanlı parçalar yazılır) ya da `failed` (`error`: "Medya dosyası çözülemedi." /
  "Medyada konuşma bulunamadı." / "Transkripsiyon modeli yüklenemedi." / "Beklenmeyen bir hata oluştu."; parça yazılmaz).
  `processing`den `ready`/`failed`e geçiş tek yönlüdür; başarısız dokümanın yeniden denenmesi yoktur (silinip yeniden
  yüklenir). Uygulama açılışında `processing`de kalmış dokümanlar `failed` ("İşlem yarıda kaldı; dosyayı yeniden
  yükleyin.") yapılır; `--reload` kod değişince süren işi öldürür.
- **Saklama.** Başarıda transkript WebVTT olarak yazılır ve dokümanın `file_path`i olur (`filename = "<başlık>.vtt"`); medya
  dosyası silinir. Başarısızlıkta da medya silinir (`file_path = ""`). `duration_s` = medyanın süresi,
  `transcript_source = "asr"`, `transcript_model` = ör. `faster-whisper/large-v3-turbo/int8`. VTT yüklemesi
  `transcript_source = "vtt"`, `transcript_model = null` yazar.
- **Erişim (#11).** Yükleme kuralları aynı (yalnızca eğitmen + `declaration`; `approved_by` doldurulur). Öğrenciler
  yalnızca `status = "ready"` dokümanları listede görür; `processing`/`failed` doküman için `/documents/{id}/…` ve
  `/sources/…` onlara 404; eğitmen hepsini (durum ve hata dahil) görür. Arama (dense, lexical, video önceliği) ve
  `AskRequest.video` yalnızca `ready` dokümanları kullanır.
- **Ses tanıma kalitesi.** `no_speech_prob > 0.6` ya da `avg_logprob < -1.0` olan segmentlerin sayısı transkriptörün
  uyarısına girer ve **sunucu günlüğüne** yazılır; `Document`'a / `IngestionReport`'a **kaydedilmez** (arka plan işinin
  raporu yok, saklamak yeni bir alan gerektirir; açık soru).

**Bilinen sınırlamalar / kalibre edilmemiş değerler.**
- `video_window_s = 120` ve `video_weight = 0.5` kalibre **edilmedi**; eval'de ("full + video time" ile "full") ayarlanacak.
- Bağlamsız sorular ("bu adımı açıklar mısın") soru metninden hesaplanan alakasızlık kapısında takılıp "materyalde yok" cevabı
  alabilir; öncelik kapıdan **sonra** devreye girer. #9 kalibrasyonunu bozmamak için bu PR'da çözülmedi.
- Boş (`""`) `media_url` gönderilirse form ayrıştırıcısı onu "verilmedi" sayar.

**Sözleşme.**

```
VideoRef   { document_id: int, time_s: float }       # time_s >= 0, videonun başından saniye
AskRequest { course_id: int, question: str, conversation_id?: int | null,
             video?: VideoRef | null }

DocumentOut (material_type = "video")  + { duration_s: float | null, media_url: str | null }
DocumentOut (tüm türler)               + { status: "processing" | "ready" | "failed",  # varsayılan "ready"
                                           error: str | null,
                                           transcript_source: "vtt" | "asr" | null,
                                           transcript_model: str | null }
Document (ORM)                         + { status: str(16) = "ready", error: text | null,
                                           transcript_source: str(8) | null, transcript_model: str(200) | null }
IngestionReport                        + { duration_s?: float | null, cues_read?: int | null,
                                           cues_skipped?: int | null, warnings: string[] }
RetrievalHit                           + { t_start: float | null, t_end: float | null }
Citation / SourceDetail (video parçası):  page = null; t_start, t_end dolu (saniye)
SourceDetail.media_url:  oynatılabilir URL (opak); arayüz t_start'a sarar
Document (ORM)                         + { duration_s: float | null, media_url: str(1000) | null }
Chunk (ORM)                            + Index(document_id, t_start)
```

Kurallar:
- Transkript (VTT/Whisper) parçaları ilgili **video** `Document`'ına bağlanır; `t_start/t_end` bu videonun zamanıdır.
  Videolar `document_id` ile ayırt edilir, zaman damgasıyla değil.
- Bir VTT dosyası `material_type = "video"` olarak kaydedilir. `transcript` türü şimdilik **kullanılmaz** (türün
  kaldırılması ya da başka bir anlam kazanması ayrı bir karardır).
- `video` verilmezse arama tüm dersi eşit tarar; verilirse yalnızca sıralamaya *yumuşak* bir öncelik uygulanır, hiçbir parça elenmez (FR-06).
- `video.document_id` aynı derse ait bir video dokümanı olmalıdır, değilse `422`. Hedef: `{code: "invalid_video"}`; hata zarfı
  (§5) gelene kadar yalnızca Türkçe `detail` döner.
- `Document.media_url` harici bir URL ise **yalnızca `https`** kabul edilir (doğrulama bu PR'da; `javascript:` gibi
  şemalar reddedilir). Alan boşsa ve medya dosyası saklanıyorsa URL dosya uç noktasından üretilir.
- `media_url` dönmezse arayüz oynatıcıyı göstermez, metin ve zamanı gösterir.
- `IngestionReport` video alanları yalnızca video/altyazı yüklemesinde dolar; sayfa tabanlı dosyalarda `null`
  (`warnings` boş liste). Mevcut alanlar değişmedi.

**Koddan farklar.**
- `AskRequest.video_time_s` → `video: VideoRef` — **[KIRICI]** (alan adı ve tip). Eski alan kaldırıldı; Pydantic
  fazla alanı yok saydığı için `video_time_s` gönderen bir istek hata almaz, alan sessizce atlanır. Tüketiciler
  ([qa/service.py](../backend/app/qa/service.py), `retrieve()`, `types.ts`) aynı PR'da güncellendi; frontend alanı
  zaten göndermiyordu. `retrieve(video_time_s=…)` → `retrieve(video: VideoPosition | None)` da **[KIRICI]** (iç API).
- `DocumentOut.duration_s`, `media_url`; `IngestionReport.duration_s/cues_read/cues_skipped/warnings`;
  `RetrievalHit.t_start/t_end`; `Document.duration_s/media_url` ve `ix_chunks_document_id_t_start` — **[ekleme]**.
- `approved_by/approved_at` (ADR-3) #11 ile geldi. `status/error/transcript_source/transcript_model` ve yerel transkripsiyon
  #14 PR d ile geldi — **[ekleme]**; mevcut dokümanlar `ready` olur, mevcut video dokümanları `transcript_source = "vtt"`.
- Davranış (VTT okuma, oynatma önceliği, `media_url`, `invalid_video`) #14 PR b+c ile geldi.

---

## 5. Ret ve hata sonuçları

**Durum:**
- **Bu PR'da tip olarak donduruldu:** `ErrorCode` ve `ApiErrorBody {detail, code}` (`schemas/common.py`, `types.ts`);
  hiçbir handler kullanmaz. `QuestionItem.outcome` alanı `str`'den `AskOutcome`'a daraltıldı (aşağıda).
- **Metin donduruldu; koda geçişi #5'in devamı:** `provider_error`, `decline_source`, SSE `error` olayının
  `code`/`retryable` alanları ve değişmezler (üreticileri `answer.py`, `qa/service.py`, `api/ask.py` değişmelidir).

**Şu an (#5, PR #66 sonrası).** `AskResponse.outcome` mevcut ve kullanılıyor:
`"answered" | "insufficient_evidence" | "unsupported" | "model_refusal" | "provider_failure"`, ayrıca `unsupported_removed`.
Frontend: [outcome.ts](../frontend/src/features/tutor/outcome.ts).

**Eksikler.**

| # | Eksik | Bugünkü etkisi |
|---|---|---|
| 1 | LLM anahtarı yok (`extractive`, `outcome="answered"`) ve LLM'e ulaşılamıyor (`provider_failure`) ayrılıyor, ama `provider_failure` anahtar geçersiz, kredi bitti, istek sınırı, ağ hatası ve kesilen cevabı tek kalıba sokuyor ([openrouter.py:82](../backend/app/llm/openrouter.py#L82)). LLM'siz alıntı `answered` sayıldığı için log/eval'de yanıltıcı. | Operasyonel neden görünmüyor; eval'de LLM'siz cevap gerçek cevap gibi sayılır |
| 2 | SSE `error` olayında kod yok (`{detail}` tek alan); "Sohbet bulunamadı" da "geçici sorun" gösteriliyor ([TutorPage.tsx:147-149](../frontend/src/pages/student/TutorPage.tsx#L147-L149)). | Kalıcı ve geçici hata ayırt edilemiyor, yeniden dene yanlış yönlendirir |
| 3 | `outcome.ts`, `decline_reason`'ı backend'in sabit `NOT_COVERED` cümlesiyle string karşılaştırıyor. | Backend metni değişirse sessizce bozulur |
| 4 | `model_refusal` yanıtı `suggested_sources` döndürmüyor (diğer retler döndürüyor). | Tutarsız yönlendirme |
| 5 | `declined` ile `outcome` arasında yazılı değişmez yok. | Çelişkili yanıt üretilebilir |
| 6 | HTTP hata gövdesi: bazı hatalar `{detail: str}`, 422 doğrulama hatası `{detail: [...]}`; frontend yalnızca string `detail` okuyor. | 422'de "İstek başarısız (422)" |

**Önerilen sözleşme.**

```
AskResponse (mevcut alanlar) + {
  provider_error: "not_configured" | "auth" | "quota" | "rate_limited"
                | "unreachable" | "truncated" | null,   # kullanıcıya gösterilmez; log/eğitmen/eval için
  decline_source: "relevance_gate" | "model" | "verification" | "refusal" | null
}

SSE error olayı:  { code: "conversation_not_found" | "internal_error",
                    detail: str, retryable: bool }

Hata zarfı (tüm uygulama hataları):  { detail: str, code: str }
```

Değişmezler (`AskResponse`):
- `declined == true` ⇔ `answer == null`.
- `outcome == "answered"` ⇒ `declined == false`, `citations` boş değil.
- `outcome == "provider_failure"` ⇒ `answer` dolu (alıntı), `mode == "extractive"`, `provider_error != null`.
- `mode == "extractive"` ve `provider_error == "not_configured"`: LLM yok.
- `outcome ∈ {insufficient_evidence, unsupported, model_refusal}` ⇒ `declined == true`; ilk ikisi `suggested_sources` döndürür;
  `model_refusal` için de döndürülmesi önerilir.
- `decline_source`: `relevance_gate` (alakasızlık kapısı), `model` (model "YOK:" dedi), `verification`
  (doğrulamadan geçemedi), `refusal` (model reddetti); `outcome="answered"` iken `null`.

Hata kodu listesi (başlangıç): `course_not_found`, `source_not_found`, `conversation_not_found`, `document_not_found`,
`unsupported_file_type`, `file_too_large`, `ingestion_failed`, `course_exists`, `no_valid_item`, `invalid_video`,
`not_authenticated`, `insufficient_role`, `not_implemented`, `validation_error`.

**Koddan farklar.**
- `provider_error`, `decline_source` — **[ekleme]** (frontend `outcome.ts` önce `decline_source`'a geçer, sonra string karşılaştırması silinir).
- SSE `error` olayına `code`, `retryable` — **[ekleme]**; `detail` kalır.
- Hata zarfına `code` — **[ekleme]**; `422 validation_error`'da `detail` artık her zaman string — **[KIRICI]** (şu an liste olabilir; hiçbir tüketici listeyi okumuyor).
- `ErrorCode`, `ApiErrorBody` — **[ekleme]**, tip olarak donduruldu; `main.py`'de hata zarfını üreten handler yazılana
  kadar hiçbir yanıt bu şekli taşımaz (mevcut yanıtlar `{detail: str}` döner). `ErrorCode` listesi yukarıdaki listeyle aynıdır.
- `QuestionItem.outcome: str` → `AskOutcome` (PR #68 etkinlik şeması) — daraltma. TS tarafı zaten `AskOutcome`'dı. Çalışma
  zamanı etkisi: `instructor/activity.py::_outcome` mesaj meta'sından gelen değeri doğrulamadan geçirir; `AskOutcome`
  dışında bir değer kayıtlıysa etkinlik endpoint'i `ValidationError` ile `500` verir. `qa/service.py` yalnızca geçerli
  değerleri yazar ve #5 öncesi kayıtlar için yedek (`answered`/`insufficient_evidence`) vardır; bu yüzden beklenen durumda
  kırılma yoktur.
- Etkinlikte (PR #68) iki tutarsızlık, bu PR'da **düzeltilmedi**: `unavailable` yalnızca `provider_failure`'ı sayar
  (anahtarsız LLM'siz alıntı `answered` sayılır); `unanswered_questions` `model_refusal`'ı almaz ama `not_generated`
  sayar (DECISIONS.md açık soru 10).
- Eval: `mode="extractive"` cevaplar `answered` sayılmaz (eval koşulları ayrı raporlanır) — **dokümantasyon / harness kuralı**.

---

## 6. Ortak dosya protokolü

Bu protokol issue #3'teki ekip kuralları ile uyumludur.

### 6.1 Ortak (hotspot) dosyalar

- `backend/app/db/models.py` ve migration'lar (`backend/migrations/versions/*`)
- `backend/app/schemas/`
- `frontend/src/api/types.ts` (ve `api/client.ts`'in sözleşmeyi etkileyen kısımları)
- `frontend/src/router.tsx`
- Uygulama başlangıcı / bağımlılık enjeksiyonu: `backend/app/main.py` (router kaydı), `backend/app/api/deps.py`, `backend/app/auth/*`
- Bağımlılık dosyaları: `backend/pyproject.toml`, `frontend/package.json`, `frontend/package-lock.json`
- `docker-compose.yml`
- Bu dokümanlar: `docs/CONTRACTS.md`, `docs/DECISIONS.md`

### 6.2 Sahiplik

- Her ortak sözleşme / ORM / router değişikliği PR'ının **aynı anda tek bir gönüllü sahibi** vardır.
  Sahip PR'ın açıklamasında ve ilgili issue'da adıyla yazılır.
- **Aynı model veya şema değişikliği bağımsız olarak iki kez yapılmaz.** Başlamadan önce ilgili issue'da kimsenin
  aynı değişikliği üstlenmediği kontrol edilir.
- Sahip, PR'ı **erken** yayınlar (taslak PR yeterli); bağımlı branch'ler PR merge olunca `main`'den güncellenir.
- Platform iş akışı (persistence ve API sınırları) ORM/migration ve API sözleşmelerini; Product iş akışı
  tarayıcı yönlendirmesini (`router.tsx`) ve TypeScript tiplerini koordine eder. Bir sözleşme iki tarafı da
  etkiliyorsa her iki iş akışından en az birer kişi onaylar.
- **İstisna (kayıt):** PR #68 (`models.py`, migration, `schemas/courses.py`, `schemas/instructor.py`, `types.ts` ve
  `router.tsx` değişiklikleri) bu protokol yürürlüğe girmeden merge edildi; protokole aykırı sayılmaz. Etkileri bu
  dokümana işlendi (§3, §5, DECISIONS.md açık sorular 5, 8–10). Bundan sonraki ortak dosya değişiklikleri protokole tabidir.

### 6.3 Akış

1. **Karar:** değişiklik önce bir issue'da alan alan önerilir (bu dokümandaki biçimle: ad, tip, değişmez, [KIRICI]/[ekleme]).
2. **Onay:** backend ve frontend tüketicilerinden en az birer kişi onaylar. Karar gerektiriyorsa `DECISIONS.md` güncellenir.
3. **Entegrasyon PR'ı:** tek sahip, tek PR: Pydantic şemaları + `types.ts` + (gerekiyorsa) tek migration +
   `501` dönen yeni router iskeletleri + güncellenen testler + bu dokümanın güncellenmiş hali.
   PR yalnızca sözleşmeyi içerir; özellik mantığı içermez.
4. **Merge:** sözleşme `main`'e girince "dondurulmuş" sayılır.
5. **Uygulama PR'ları** onaylanmış sözleşmeden başlar ve ortak dosyalara dokunmaz. Gerekli bir değişiklik
   sıradaki entegrasyon PR'ına istek olarak (issue yorumu) eklenir.
6. **Kırıcı değişiklik** (yeniden adlandırma, silme, tip daraltma, davranış değişikliği): iki tarafın tüketici kodu
   aynı PR'da güncellenir ve PR açıklamasında [KIRICI] maddeleri listelenir.

### 6.4 Migration kuralları

- Her zaman tek `alembic` başı (`alembic heads` bir satır).
- Merge edilmiş migration düzenlenmez; düzeltme yeni migration olur.
- Model değişikliği ile migration aynı PR'dadır.
- Öneri: CI'da `alembic upgrade head` ve `alembic check` adımları.

### 6.5 Kanban ve PR kuralları (issue #3'ten)

- Pull-based Kanban: **Backlog → Ready → In progress → In review → Done**.
- Kişi başı aynı anda tek aktif iş. Ekipte en fazla 5 iş *In progress*, 5 iş *In review*.
- PR'lar tek bir issue'ya ya da küçük, belgelenmiş bir devir teslime odaklıdır; başkasının dosyalarında geniş
  format/yeniden adlandırma değişikliği yapılmaz.
- **Definition of Done:** kabul kriterleri gösterilir; anlamlı testler ve mevcut kontroller geçer; gerçek
  sağlayıcı/veri yolları çalışır; erişim/onay ve kaynak izi korunur; kullanıcı metinleri anlaşılır; gerekli
  değerlendirme kanıtı eklenir; bir arkadaş PR'ı inceler; doküman gerçek davranışı yansıtır.
  Ders içeriği ve tanımlanabilir öğrenci verisi public repoya girmez.
- Çalışma zamanında mock/demo veri veya sahte üretilmiş geri bildirim kullanılmaz; eksik dış girdiler açıkça kaydedilir (§7).

### 6.6 Öneri: Playwright testleri CI'da

`frontend/e2e/` testleri (#7) repoda var, ama [ci.yml](../.github/workflows/ci.yml) frontend işinde yalnızca `lint` ve `build`
çalışıyor; yani bu testler bugün hiçbir PR'ı korumuyor. **Öneri:** ayrı bir CI işi ile e2e'nin çalıştırılması
(`docker-compose.e2e.yml` zaten mevcut). Bu bir öneridir; bu çalışmada `ci.yml` değiştirilmedi ve değiştirme
kararı ekibe aittir.

---

## 7. Çalışma zamanında hâlâ mock olan veriler

Yok. Son mock olan kimlik doğrulama (`services/authService.ts`, `mock/users.ts`) #12'de backend oturumuna
bağlandı ve `src/mock/` kaldırıldı. Ekranlarda sahte sayı ya da sahte içerik gösterilmez; backend'i olmayan
özellikler (pratik, öğrenci listesi, sık hatalar) ilgili API hazır olunca gerçek veriyle eklenir.

---

## 8. Ders içeriği bölümleri (OCW düzeni)

Ders sayfası MIT OpenCourseWare gibi bölümlere ayrılır: İzlence, Takvim, Video dersler, Ders notları, Sınavlar,
Pratik problemler, Ödevler. Bölümler `frontend/src/features/courses/sections.ts`'te tanımlıdır. Materyal bölümleri
dokümanları türüne göre süzer, izlence ve takvim ayrı bir endpoint'ten gelir. Hepsi **[ekleme]**: mevcut alan ve
endpoint'ler değişmez.

| Değişiklik | Backend | Frontend |
|---|---|---|
| Yeni materyal türleri | `MaterialType.ASSIGNMENT = "assignment"`, `PRACTICE_PROBLEM = "practice_problem"` | `MaterialType` birleşimi, `MATERIAL_LABELS` ("Ödev", "Pratik problem") |
| İzlence / takvim kolonu | `courses.syllabus`, `courses.calendar` (JSONB, boş olabilir); migration `c4f1d2a8e6b0`, kimlik dalıyla birleştirme `e7b2c9d4f1a3` | — |
| Yeni endpoint | `GET /courses/{id}/outline` → `CourseOutline`; dersin her üyesi görür, üye olmayana 404, oturumsuza 401 | `api.courseOutline`, `courseService.outline` |
| Yeni adresler | — | `…/courses/:id/{syllabus,calendar,videos,lecture-notes,quizzes,practice-problems,assignments}` (iki rol) |

```
CourseOutline   { syllabus: SyllabusBlock[] | null, calendar: CourseCalendar | null }
SyllabusBlock   { type: "heading" | "paragraph" | "list" | "table", text, items, rows }   # tabloda ilk satır başlık
CourseCalendar  { intro: str | null, columns: str[], rows: CalendarCell[][] }
CalendarCell    { lines: str[], span: int }
```

- Değişmez: izlence ve takvim **düz metindir**; dışarıdan gelen HTML saklanmaz ve sayfaya basılmaz.
- Şimdilik yalnızca `python -m app.scripts.import_ocw <paket>` doldurur. Eğitmenin düzenlemesi sonraki iştir.
  Betikle açılan dersin üyesi yoktur; `create_instructor --course <KOD>` ile bir eğitmene bağlanır.
- Bölüm ↔ tür: Video dersler = `video`, `transcript`; Ders notları = `notes`, `slides`, `textbook`;
  Sınavlar = `past_exam`; Pratik problemler = `practice_problem`; Ödevler = `assignment`.

---

## 9. AI Tutor turu (ADR-7, öneri)

> §8 numarası PR #75'in ders bölümleri eklemesine ayrıldı. Bu bölüm **[ekleme]**; mevcut sözleşmelerde kırıcı
> değişiklik yok. Tipler: `backend/app/schemas/tutor.py`. Frontend karşılığı (`types.ts`) arayüz işiyle eklenir.

**Uç noktalar.** `POST /tutor/turn` (tek cevap) ve `POST /tutor/turn/stream` (SSE). Yetki `/ask` ile aynı: ders
üyeliği, güncel aydınlatma onayı, sohbet sahipliği (404 `conversation_not_found`). Sohbetler `/ask` ile aynı
tablolardadır.

```text
TutorTurnRequest  { course_id, message (1–2000), conversation_id?, video?: VideoRef }
TutorTurnResponse { conversation_id, blocks: TutorBlock[], trace: TurnTrace }

TutorBlock (type ile ayrılır; her biri provenance taşır)
  course_answer        provenance=course   { response: AskResponse }        // /ask ile aynı içerik
  general_explanation  provenance=general  { text, check: "unchecked"|"checked", notice, model }
  practice             provenance=course   { item: PracticeItem }   // anahtarsız; cevap §2 uç noktasıyla
  clarification        provenance=none     { question (≤300), options (≤4) }
  notice               provenance=none     { kind, text }  // greeting | off_topic | graded_work
                                                           // | not_covered | unavailable | failure
  follow_ups           provenance=none     { items: [{action, label, message}] }  // simpler | example

TurnTrace { mode: "orchestrated"|"direct", orchestrator_model, fallback_reason,
            steps: [{tool, args, status, duration_ms}],
            usage: [{model, purpose, input_tokens, output_tokens, thought_tokens, cached_tokens, cost_usd}],
            cost_usd }
```

**SSE olayları.** `status {tool, label}` → `retrieval {block_index, hits}` → `delta {block_index, text}` (taslak)
→ `block {index, block}` (doğrulanmış; aynı indeksteki taslağın yerini alır) → … → `done TutorTurnResponse`;
hata olursa `error {detail}`.

**Arama.** `answer_from_course` ve `generate_practice` argümanlarında `search_query`: sorunun ders materyalinin
dilindeki karşılığı (Türkçe soru, İngilizce not). Arama bununla, cevap öğrencinin sorusuyla yapılır. Kaynaklı cevapta
20 aday hızlı modelle yeniden sıralanır, en iyi 6'sı üreticiye gider (`retrieval/rerank.py`). `AskResponse`'a
**[ekleme]** `coverage_gap`: kısmi cevapta kaynakların kapsamadığı kısım (alıntısız not).

**Pratik turu.** `generate_practice` çalışırken `status` olayları gerçek adımları bildirir: "Konuyu anlatan bölüm
seçiliyor…" → "Soru yazılıyor…" → "Soru bağımsız çözümle kontrol ediliyor…" (aday elenirse "yeni bir soru
yazılıyor…"). "Bu konuda beni test et" isteğinde önce bu turun ya da sohbetteki son kaynaklı cevabın alıntıladığı
parçalar denenir (hızlı modelle 2+ puan alan varsa arama yapılmaz); yoksa normal arama.

**Değişmezler.**
- Öğrenciye görünen içerik yalnızca bloklardan gelir; orkestratörün serbest metni hiçbir yanıtta yoktur.
- Pratik sorusunun anahtarı, referans cevabı ve açıklaması hiçbir tur yanıtında ve orkestratöre giden sonuçta yoktur.
- `general_explanation` her zaman `notice` ile, alıntısız gösterilir; kaynaklı cevap gibi sunulmaz.
- `follow_ups` metinleri sabittir; tıklanınca `message` yeni tur olarak gönderilir.
- `trace` değerlendirme ve hata ayıklama içindir; öğrenci arayüzünde gösterilmez.
- Asistan mesajının `meta`'sı: kaynaklı cevap özeti (`outcome`, `declined`, `cited_source_ids`; eğitmen etkinliği
  okur), `tutor: true`, `blocks`, `trace`. Kaynaklı cevap içermeyen tur `counted: false` taşır ve soru sayılmaz.
