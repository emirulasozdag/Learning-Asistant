# Ekip kararları (ADR)

> Issue #6 — *[S01-C] Agree SRS, shared contracts and identity/consent decisions*.
> Bu dosya, uygulamaya başlamadan önce ekibin vermesi gereken beş kararı ve açık soruları kaydeder.
> Tüm kararların durumu şu an **Önerildi**. Karar tarihi ve katılanlar, ekip karar verince doldurulur.
> Sözleşmeler (alan adları, tipler): [CONTRACTS.md](CONTRACTS.md). Gereksinim durumu: [ANALYSIS.md §14.1](ANALYSIS.md).

**Bu dosya hukuki görüş değildir.** KVKK ile ilgili maddeler (ADR-4, ADR-5) mühendislik düzeyinde bir öneridir.
Aydınlatma metni, açık rıza metni, saklama süresi ve yurt dışına aktarım için bölüm / etik kurul / üniversite
hukuk birimi onayı alınmalıdır (bkz. ANALYSIS §13.1, "KVKK" riski).

| ADR | Konu | Durum | Karar tarihi | Katılanlar |
|---|---|---|---|---|
| 1 | Kimlik doğrulama yöntemi | Önerildi | — | — |
| 2 | Ders üyeliği | Önerildi | — | — |
| 3 | Onaylı materyalin dahil edilmesi | Önerildi | — | — |
| 4 | Onay ve saklama (KVKK) | Önerildi | — | — |
| 5 | Hosted modelle veri paylaşımı | Önerildi | — | — |

---

## ADR-1 — Kimlik doğrulama yöntemi

**Bağlam.** Frontend'deki giriş/kayıt ekranları şu an sahte: oturum ve hesaplar tarayıcının `localStorage`'ında
tutuluyor ([authService.ts](../frontend/src/services/authService.ts)), rol kontrolü yalnızca istemcide
(`RequireRole`). Backend'de kimlik yok: [auth/dependencies.py](../backend/app/auth/dependencies.py) iskelet,
hiçbir endpoint kullanıcıyı tanımıyor. Kayıt formunda kullanıcı kendi rolünü seçebiliyor. FR-17 ve
issue #11 (backend erişim kontrolü), #12 (frontend'de gerçek kimlik) bu karara bağlı.
Takım küçük ve proje bir dönemlik.

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Kendi hesap sistemi** (e-posta + şifre, argon2 özeti, httpOnly oturum çerezi) | Bir dönemde bitirilebilir; dış bağımlılık yok; test etmek kolay | Şifre saklama sorumluluğu bizde; e-posta doğrulama ve şifre sıfırlama ek iş |
| **B. Üniversite SSO** | Gerçekçi üretim çözümü; şifre tutulmaz | Üniversite BİDB onayı ve entegrasyon takvimi bizim elimizde değil; bir dönem için riskli |
| **C. Alan adı kısıtlı Google OAuth** | Şifre tutulmaz; hızlı | Üniversite e-postasının bu yolu destekleyip desteklemediği belirsiz; harici sağlayıcıya bağımlılık |

**Öneri: A.**
- Öğrenci kendi hesabını açar. **Eğitmen ve TA rolü kayıt formundan seçilemez**; eğitmen hesabı yönetici/seed ile
  açılır, TA'yı dersin eğitmeni ekler (ADR-2).
- Oturum sunucu tarafında doğrulanır; kimlik hiçbir zaman istek gövdesinde gelmez (CONTRACTS.md §3).
- Çalışma zamanında demo/mock hesap kullanılmaz (issue #3 DoD). Geliştirme ve test hesapları seed betiğiyle
  oluşturulur ve üretim ortamında kapalıdır.
- B, sonraki iterasyonda aynı `/me` sözleşmesinin arkasına eklenebilir.

**Sonuçları.** `User` tablosu ve oturum mekanizması gerekir; `get_current_user` gerçekleşir; frontend'de `authService`
gerçek API'ye geçer (#12). Mevcut `register` ekranından rol seçimi kalkar.

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## ADR-2 — Ders üyeliği

**Bağlam.** Ders izolasyonun birimi (FR-04), ama bugün her istek her dersi kullanabiliyor:
`GET /courses` tüm dersleri döndürüyor, `CourseSummary.role` her zaman `null`. Rol *ders başına* olmalı
(bir kişi bir derste eğitmen, başka derste öğrenci olabilir; backend'deki `CurrentUser.roles` bunu zaten
öngörüyor).

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Katılım kodu** (eğitmen dersi açınca kod üretilir, öğrenci kodla katılır) | Basit; gönüllü pilot modeline uyar; eğitmene liste hazırlama yükü yok; sızarsa kod yenilenir | Kod paylaşılırsa yetkisiz katılım olabilir |
| **B. Eğitmen e-posta listesiyle ekler** | Daha kontrollü | Eğitmene iş çıkarır; kişisel veri listesi toplanır/tutulur |
| **C. Açık** (giriş yapan herkes her dersi görür) | En basit | FR-17 ve ders izolasyonu hedefiyle çelişir; materyal erişimi kontrolsüz |

**Öneri: A.**
- Dersi oluşturan kullanıcı o dersin `instructor`'ı olur. TA'yı eğitmen ekler.
- Üyelik `Enrollment(user_id, course_id, role)` ile tutulur; kod yenilenebilir ve süresi dolabilir.
- `GET /courses` yalnızca üye olunan dersleri döndürür ve `role` zorunludur.
- Üye olmayan kullanıcı için ders, kaynak, doküman ve sohbet endpoint'leri aynı yanıtı verir
  (varlığını sızdırmamak için 404; ayrıntı CONTRACTS.md §3).

**Sonuçları.** Yeni tablo ve migration (ortak dosya, tek sahipli PR: CONTRACTS.md §6); #11'in kapsamını belirler.

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## ADR-3 — Onaylı materyalin dahil edilmesi

**Bağlam.** Proje yalnızca eğitmenin onayladığı materyale dayanır (ANALYSIS §6, §13.1). Bugün yüklenen her
dosya doğrudan indekslenir; "onaylı" bir durum yok ve yükleme endpoint'i kimlik doğrulamıyor.
Geçmiş sınavlar ile "aktif sınav içeriği" ayrımı ve ders kitabı telifi eğitmenle netleşecek (WP1, #8).

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Örtük onay**: yalnızca eğitmen yükleyebilir; yükleme onay sayılır | En az kod; eğitmen iş akışına uyar | TA yüklerse onay garantisi yok; onay izi yok |
| **B. Açık durum**: `draft → approved`; aramaya yalnızca onaylı parçalar girer | Net denetim izi; TA yükleyebilir | Ek arayüz ve sorgu koşulu; her aramada filtre |
| **C. Yalnızca dokümandaki onaylı liste (WP1)** | Kod yok | Sistem onaysız dosyayı engelleyemez; DoD'daki "kaynak izi korunur" ile uyumsuz |

**Öneri: A + yükleme anında beyan.**
- Yalnızca `instructor` yükleyebilir. Yükleme formunda beyan kutusu: *"Bu materyali bu derste kullanma yetkim var;
  aktif sınav içeriği değil."*
- `Document` üzerinde `approved_by` ve `approved_at` kaydedilir.
- TA'nın yüklemesine izin verilecekse B'ye geçilir (aynı alanlar kullanılır, `approved_at` boşken arama dışı kalır).
- Ders içeriği repoya girmez ve dışa aktarılan eval verisinde yer almaz (issue #3 DoD).

**Sonuçları.** `Document`'a iki alan (migration); yükleme endpoint'inde rol kontrolü (#11).

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## ADR-4 — Onay ve saklama (KVKK)

> Bu bölüm hukuki görüş değildir; yukarıdaki uyarıya bakın.

**Bağlam.** Öğrenciler soru soruyor, pratik yapıyor ve cevap yazıyor. Pilotta öğrenme kaydı (FR-15), eğitmen
analitiği (FR-16) ve insan değerlendirme verisi (~60 öğrenci cevabı, QWK için) toplanacak. ANALYSIS §6 bunu
"yalnızca opt-in, anonimleştirilmiş, KVKK uyumlu" olarak ister. Bugün sohbet ve mesajlar kullanıcıya bağlı değil
ve saklama süresi tanımsız.

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Tek onay** (onay vermeyen sistemi kullanamaz) | Basit | Onay vermeyen öğrenci hizmetten mahrum kalır; onay "serbest" olmaz |
| **B. İki katman**: hizmet için aydınlatma metni (sohbet geçmişi, takip soruları); araştırma/analiz kaydı için ayrı opt-in, varsayılan kapalı | Hizmet ile araştırma ayrılır; opt-in gerçekten isteğe bağlı | İki bayrak, iki metin, sürüm takibi |
| **C. Hiç kayıt tutma** | En az veri | Takip soruları (FR-10), öğrenme kaydı (FR-15) ve eğitmen görünümü (FR-16) mümkün olmaz |

**Öneri: B.**
- Aydınlatma metni ilk girişte gösterilir; sürümü (`policy_version`) ve onay zamanı kaydedilir.
- `research_logging` varsayılan **kapalı**. Kapalıyken pratik denemeleri öğrenme kaydına ve eğitmen analitiğine yazılmaz
  (öğrencinin kendi pratik ekranı için gereken en az bilgi hariç; ayrıntı uygulamada netleşir).
- Eğitmen analitiği toplu ve anonimdir; kişi bazlı gösterim yoktur.
- "Verilerimi sil" yolu bulunur.
- Eval ve rapor için dışa aktarılan veri takma adlıdır ve public repoya girmez.
- LLM'e ad, e-posta veya kimlik göndermeyiz (ADR-5).
- Saklama süresi *dönem sonu + tanımlı bir ek süre* olarak önerilir; kesin tarih açık soru olarak aşağıda.

**Sonuçları.** `Consent` kaydı (veya kullanıcı üzerinde alanlar), `Me.consent` (CONTRACTS.md §3), yazma
yollarında onay kontrolü (#11).

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## ADR-5 — Hosted modelle veri paylaşımı

> Bu bölüm hukuki görüş değildir; yukarıdaki uyarıya bakın.

**Bağlam.** Cevaplar bugün OpenRouter üzerinden Claude ile üretiliyor
([llm/gateway.py](../backend/app/llm/gateway.py)). Hosted modele giden veri: öğrenci sorusu, getirilen ders
parçaları ve son 3 turun sohbet geçmişi. Pratik/değerlendirme eklenince öğrenci cevapları da gidecek (FR-13).
FR-14 için generator'dan farklı bir model ailesi (judge) gerekiyor. `local.py` iskelet.

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Hosted** (kişisel veri göndermeden) | Şu anki kodla aynı; kalite yüksek; donanım gerekmez | OpenRouter araya ikinci bir taraf ekler; sağlayıcıların veri saklama/eğitim ayarları doğrulanmalı (**doğrulanmadı**); ders materyali dışarı gider |
| **B. Yalnızca local** | Gizlilik açısından en iyisi | Kalite ve donanım riski; judge için ikinci model yine gerekir |
| **C. Hibrit** (soru-cevap hosted; öğrenci cevabı değerlendirme local ya da ayrı opt-in) | Hassas veri sınırlanır | Kural ve iki adapter bakımı; local kalite riski |

**Öneri: Iteration 1 için A, sınırlarıyla.**
- Hosted'a yalnızca soru, getirilen ders parçaları ve sohbet geçmişi gider; **ad, e-posta, kullanıcı/oturum
  kimliği gitmez**.
- Öğrenci cevaplarının da hosted'a gittiği aydınlatma metninde açıkça yazılır (ADR-4).
- Ders materyalinin hosted modele gönderilmesi için eğitmenin açık onayı alınır (ADR-3'teki beyana eklenir).
- Sağlayıcı ayarları (veri saklama, eğitimde kullanmama) kayıt altına alınmadan pilot başlamaz; bu kontrol
  henüz yapılmadı.
- API anahtarı yalnızca `.env`'de tutulur, repoya girmez.
- Judge için farklı model ailesinden ikinci bir sağlayıcı gerekir; seçimi FR-14 işinde yapılır.

**Sonuçları.** Gateway'e gönderilen yükün (payload) kimlik içermediğini gösteren bir test; sağlayıcı seçimi
ve saklama ayarları için kısa bir kayıt.

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## Açık sorular

Bunlar ekip ya da dış taraf (eğitmen, bölüm) cevabı bekleyen konulardır. Cevaplanana kadar varsayım yapılmaz.

| # | Soru | Kim cevaplar | Etkilediği iş |
|---|---|---|---|
| 1 | **Video barındırma.** Videolar nerede (LMS, YouTube, dosya)? Henüz bilinmiyor; eğitmenle konuşulacak (#8, materyal envanteri). `media_url` barındırma yönteminden bağımsız tasarlandı (CONTRACTS.md §4); yöntem belli olunca yalnızca URL üretimi ve oynatıcı bileşeni etkilenir. | Eğitmen / #8 | FR-06, FR-18 video, PR B kapsamı dışı |
| 2 | **Ders kitabı telifi.** Hangi kitap bölümleri indekslenebilir ve hosted modele gönderilebilir? | Eğitmen / bölüm | ADR-3, ADR-5, WP1 |
| 3 | **Saklama süresinin kesin tarihi.** Sohbet, öğrenme kaydı ve eval verisi ne zaman silinecek veya anonimleştirilecek? | Ekip + bölüm/etik kurul | ADR-4 |
| 4 | **FR-07 (task router).** Görev başına ayrı endpoint'ler (`/ask`, `/practice`, `/practice/{id}/answer`) FR-07'yi karşılamış sayılır mı? Sayılmazsa `routing/router.py` gerçekleştirilmeli. | Ekip | FR-07 kabul kanıtı |
| 5 | **Kaynak ve doküman endpoint'lerinin dersle sınırlı olmaması — güvenlik açığı, #11'de kapatılmalı.** `GET /sources/{source_id}`, `GET /documents/{id}/chunks`, `/documents/{id}/file`, `/documents/{id}/pages/{n}.png` ve `DELETE /documents/{id}` ders üyeliği kontrol etmiyor; chunk/doküman kimliğini bilen herkes herhangi bir dersin içeriğini okuyabilir (silme dahil). Ayrıca `POST /courses/{id}/materials` ve `POST /courses` kimlik doğrulamasız. Aynı şekilde, sohbetler (`conversation_id`) bir kullanıcıya bağlı olmadığı için kimliği bilinen sohbet okunabilir. | #11 | FR-04, FR-10, FR-17 |
| 6 | **Judge modeli ve hosted sağlayıcı ayarları.** Hangi model ailesi, hangi sağlayıcı ve veri saklama ayarları? | Ekip | ADR-5, FR-14 |
| 7 | **Ana sayfa yönlendirmesi.** Hem eğitmen hem öğrenci üyeliği olan kullanıcı hangi ana sayfaya gider? (Öneri: en az bir derste eğitmense eğitmen ana sayfası, derste rol değiştirme bağlantısıyla.) | Ekip (Product) | #12 |
