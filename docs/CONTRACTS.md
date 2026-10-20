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
- `SourceDetail.course_id` — **[ekleme]**. Metin donduruldu; koda geçişi **#11** (erişim kontrolü ile birlikte;
  [lookup.py](../backend/app/sources/lookup.py) doldurmalıdır).
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

Pratik endpoint'leri (`POST /practice`, `POST /practice/{id}/answer`) hâlâ `501` döner. Issue #3 DoD'si gereği
çalışma zamanında mock kullanılmaz (bkz. §7); #17 gerçek API'ye bağlanır.

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

UserOut        { id: int, name: str, email: str, title: str | null }
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

**Durum:** Metin donduruldu; koda geçişi video barındırma kararından sonra (DECISIONS.md açık soru 1, #8 materyal
envanteri). Bu PR'da tip eklenmedi. Videonun nerede barındırıldığı bilinmiyor; `media_url` bu yüzden barındırma
yönteminden bağımsız, opak bir URL olarak tanımlıdır.

**Şu an.**
- `MaterialType` içinde `video` ve `transcript` var, ama video yüklemek/oynatmak için hiçbir yol yok
  (yükleme yalnızca `.pdf`, `.pptx`; `vtt_parser.py` iskelet).
- `AskRequest.video_time_s: float | null` kabul ediliyor ama `retrieve()` onu kullanmıyor; frontend göndermiyor.
  Hangi videoya ait olduğu belirsiz.
- `Chunk.t_start/t_end` sütunları var, dolduran yol yok. `Citation` ve `SourceDetail` `t_start/t_end` taşıyor.
- `SourceDetail.media_url` yalnızca dosya URL'si olarak dolduruluyor (PDF/PPTX).

**Önerilen sözleşme.**

```
VideoRef   { document_id: int, time_s: float }       # time_s >= 0, videonun başından saniye
AskRequest { course_id: int, question: str, conversation_id?: int | null,
             video?: VideoRef | null }               # video_time_s kaldırılır

DocumentOut (material_type = "video")  + { duration_s: float | null, media_url: str | null }
Citation / SourceDetail (video parçası):  page = null; t_start, t_end dolu (saniye)
SourceDetail.media_url:  oynatılabilir URL (opak); arayüz t_start'a sarar
```

Kurallar:
- Transkript (VTT/Whisper) parçaları ilgili **video** `Document`'ına bağlanır; `t_start/t_end` bu videonun zamanıdır.
- `video` verilmezse arama tüm dersi eşit tarar; verilirse yalnızca sıralamaya *yumuşak* bir öncelik uygulanır, hiçbir parça elenmez (FR-06).
- `video.document_id` aynı derse ait olmalıdır, değilse `422 {code: "invalid_video"}`.
- `media_url` dönmezse arayüz oynatıcıyı göstermez, metin ve zamanı gösterir.

**Koddan farklar.**
- `AskRequest.video_time_s` → `video: VideoRef` — **[KIRICI]** (alan adı). Pratikte etkisi yok: frontend göndermiyor,
  backend yok sayıyor. Alan kaldırılırsa [qa/service.py](../backend/app/qa/service.py) `request.video_time_s` okuduğu için
  servis kodu da değişmelidir; bu yüzden **bu PR'da yapılmadı**. Geçiş dönemi gerekmez; alanı kaldıran iş `AskRequest`'in
  tüm kullanım yerlerini ve testleri aynı PR'da günceller.
- `DocumentOut.duration_s`, `media_url` — **[ekleme]**; üretici (`to_document_out`) değişeceği için bu PR'da yapılmadı.
- Davranış (video yükleme/oynatma/öncelik) bu PR'da **yoktur**; ilgili işlerde gerçekleşir.

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

Issue #3'e göre çalışma zamanında mock/demo veri kullanılmaz. PR #68, `courseStats`, `dashboard`, `practice` ve
`tutor` mock'larını ve bunları kullanan `dashboardService`/`practiceService`'i sildi; ekranlarda sahte sayı ya da
sahte içerik gösterilmez ([mock/README.md](../frontend/src/mock/README.md)). Kalan tek mock:

| Mock | Dosya | Gerçek kaynak | Bağlı iş |
|---|---|---|---|
| Hesaplar, giriş, oturum (localStorage) | `services/authService.ts`, `mock/users.ts` | ADR-1; §3 | #12 (backend: #11) |

Backend'i olmayan özellikler (pratik, öğrenci listesi, sık hatalar) ilgili API hazır olunca gerçek veriyle eklenir
(#17 ve ilgili işler). Ders istatistikleri artık mock değildir; öğrenci sayısı gibi alanlar kullanıcı/üyelik
verisi (#11) gelene kadar gösterilmez.
