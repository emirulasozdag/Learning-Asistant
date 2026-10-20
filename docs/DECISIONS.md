# Ekip kararları (ADR)

> Issue #6 — *[S01-C] Agree SRS, shared contracts and identity/consent decisions*.
> Bu dosya, uygulamaya başlamadan önce ekibin vermesi gereken beş kararı ve açık soruları kaydeder.
> Beş karar da ekip tarafından **2026-10-20'de kabul edildi**. Katılanlar: Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri).
> Sözleşmeler (alan adları, tipler): [CONTRACTS.md](CONTRACTS.md). Gereksinim durumu: [ANALYSIS.md §14.1](ANALYSIS.md).

**Bu dosya hukuki görüş değildir.** KVKK ile ilgili maddeler (ADR-4, ADR-5) mühendislik düzeyinde bir öneridir.
Aydınlatma metni, açık rıza metni, saklama süresi ve yurt dışına aktarım için bölüm / etik kurul / üniversite
hukuk birimi onayı alınmalıdır (bkz. ANALYSIS §13.1, "KVKK" riski).

| ADR | Konu | Durum | Karar tarihi | Katılanlar |
|---|---|---|---|---|
| 1 | Kimlik doğrulama yöntemi | Kabul edildi | 2026-10-20 | Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri) |
| 2 | Ders üyeliği | Kabul edildi | 2026-10-20 | Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri) |
| 3 | Onaylı materyalin dahil edilmesi | Kabul edildi | 2026-10-20 | Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri) |
| 4 | Onay ve saklama (KVKK) | Kabul edildi | 2026-10-20 | Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri) |
| 5 | Hosted modelle veri paylaşımı | Kabul edildi | 2026-10-20 | Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri) |
| 6 | Transkripsiyon: yerel faster-whisper | Önerildi | — | — |
| 7 | AI Tutor mimarisi, köken politikası ve Gemini | **Önerildi** | — | Mehmet Akif Kurt (@saintpeterslibiri, öneren) |

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

**Karar: A.**
- Öğrenci kendi hesabını açar. **Eğitmen ve TA rolü kayıt formundan seçilemez**; eğitmen hesabı yönetici/seed ile
  açılır, TA'yı dersin eğitmeni ekler (ADR-2).
- Oturum sunucu tarafında doğrulanır; kimlik hiçbir zaman istek gövdesinde gelmez (CONTRACTS.md §3).
- Çalışma zamanında demo/mock hesap kullanılmaz (issue #3 DoD). Geliştirme ve test hesapları seed betiğiyle
  oluşturulur ve üretim ortamında kapalıdır.
- B, sonraki iterasyonda aynı `/me` sözleşmesinin arkasına eklenebilir.

**Sonuçları.** `User` tablosu ve oturum mekanizması gerekir; `get_current_user` gerçekleşir; frontend'de `authService`
gerçek API'ye geçer (#12). Mevcut `register` ekranından rol seçimi kalkar.

**Durum:** Kabul edildi · **Karar tarihi:** 2026-10-20 · **Katılanlar:** Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri)

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

**Karar: A.**
- Dersi oluşturan kullanıcı o dersin `instructor`'ı olur. TA'yı eğitmen ekler.
- Üyelik `Enrollment(user_id, course_id, role)` ile tutulur; kod yenilenebilir ve süresi dolabilir.
- `GET /courses` yalnızca üye olunan dersleri döndürür ve `role` zorunludur.
- Üye olmayan kullanıcı için ders, kaynak, doküman ve sohbet endpoint'leri aynı yanıtı verir
  (varlığını sızdırmamak için 404; ayrıntı CONTRACTS.md §3).

**Sonuçları.** Yeni tablo ve migration (ortak dosya, tek sahipli PR: CONTRACTS.md §6); #11'in kapsamını belirler.

**Durum:** Kabul edildi · **Karar tarihi:** 2026-10-20 · **Katılanlar:** Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri)

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

**Karar: A + yükleme anında beyan.**
- Yalnızca `instructor` yükleyebilir. Yükleme formunda beyan kutusu: *"Bu materyali bu derste kullanma yetkim var;
  aktif sınav içeriği değil."*
- `Document` üzerinde `approved_by` ve `approved_at` kaydedilir.
- TA'nın yüklemesine izin verilecekse B'ye geçilir (aynı alanlar kullanılır, `approved_at` boşken arama dışı kalır).
- Ders içeriği repoya girmez ve dışa aktarılan eval verisinde yer almaz (issue #3 DoD).

**Sonuçları.** `Document`'a iki alan (migration); yükleme endpoint'inde rol kontrolü (#11).

**Durum:** Kabul edildi · **Karar tarihi:** 2026-10-20 · **Katılanlar:** Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri)

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

**Karar: B.**
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

**Durum:** Kabul edildi · **Karar tarihi:** 2026-10-20 · **Katılanlar:** Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri)

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

**Karar: Iteration 1 için A, sınırlarıyla.**
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

**Durum:** Kabul edildi · **Karar tarihi:** 2026-10-20 · **Katılanlar:** Nisanur İlhan (öneren), Emir Ulaş Özdağ (@emirulasozdag), Mehmet Akif Kurt (@saintpeterslibiri)

---

## ADR-6 — Transkripsiyon: yerel faster-whisper

**Bağlam.** Altyazısı olmayan ders videosu/sesi de aranabilir olmalı (FR-03). Ses, kişisel veri taşıyabilir (eğitmenin sesi,
bazen öğrenci sesi); ADR-5 hosted modele giden verinin sınırlı tutulmasını ister.

**Karar (öneri).** Transkripsiyon **yerel** çalışır: faster-whisper, CPU, `int8`; hosted ses API'si kullanılmaz. Dil dersin
dilidir (otomatik algılama yok); `vad_filter` açık, `condition_on_previous_text` kapalı (sessizlikte uydurma metni azaltır).
Özellik **varsayılan kapalıdır** (`TRANSCRIPTION_MODEL` boş): kapalıyken eğitmenden `.vtt` istenir. Açıksa iş arka planda
sürer, dokümanda `status` ve `error` tutulur; transkript WebVTT olarak saklanır, medya dosyası silinir.

**Sonuçları.** İmaj büyür (faster-whisper + CTranslate2 + PyAV), ilk açılışta model iner (`large-v3-turbo` ~1,6 GB), CPU'da
uzun dersler dakikalar sürer. Ses sunucudan çıkmaz.

**Açık soru.** Model seçimi (`large-v3-turbo` / `small` / `tiny`) Türkçe ders sesinde **WER ölçümüyle doğrulanmadı**; pilot
öncesi gerçek ders kayıtlarında ölçülmeli.

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** —

---

## ADR-7 — AI Tutor mimarisi: orkestratör + araçlar, köken politikası ve Gemini

> **Öneri.** Ekip onayı bekliyor; kod `/tutor` uç noktasında ve varsayılan ayarlarla bunu uygular.
> `/ask` ve değerlendirme hattı değişmedi.

**Bağlam.** Ürün arayüzde öğrenciyle konuşan, öğreten ve içerik üreten bir tutor olacak; yetenekler M2–M5'te
artıyor (pratik, değerlendirme, görsel kare, ses, interaktif materyal). Bugünkü hat tek yönlü (`/ask`) ve FR-07
task router iskelet (açık soru 4). Ürünün iddiası "kontrol edilmeden gösterilmez" ve **ölçülmüş** güvenilirlik.
Öte yandan kaynakta olmayan her soruya ret, kötü bir öğretmen deneyimi: DSA notları "log n"i bilinen sayıyorsa
"log n ne demek?" diye soran öğrenci ret alıyor. Ayrıca bugünkü alıntı kontrolü yalnızca etiketin varlığına
bakıyor; model genel bilgisini `[S1]` ile etiketlerse geçiyor (#10 bunu kapatacak). Ekip LLM sağlayıcısı olarak
Gemini'yi kullanmak istiyor.

**Seçenekler.**

| | Artıları | Eksileri |
|---|---|---|
| **A. Görev başına sabit uç noktalar** (bugünkü) | Basit; ölçümü kolay | Konuşma içinde yetenek seçimi yok; her yetenek için ayrı arayüz akışı |
| **B. Serbest ajan** (model hem araç seçer hem içerik yazar) | Esnek | Kontrolsüz içerik yolu: cite-or-decline delinir; ölçüm tekrarlanamaz |
| **C. Kısıtlı orkestratör** (model araç seçer; içerik yalnızca araçlardan; kontrol araçların içinde) | Konuşma + kontrol + ölçüm birlikte | Orkestratörün ayrıca ölçülmesi gerekir; turda ek model çağrısı |

**Karar (öneri): C.**
- **Orkestratör içerik yazmaz.** Her adımda bir araç çağırmak zorundadır (function calling, mod `ANY`); serbest
  metni öğrenciye gitmez. Öğrenciye giden her şey bir araçtan gelen bloktur (`schemas/tutor.py`).
- **Araçlar:** `answer_from_course` (kaynaklı hat), `generate_practice` (kontrol edilmiş pratik sorusu, #16),
  `explain_general` (bayrakla), `ask_clarification`, `reply_notice` (sabit metinler), `finish`. Cevap
  değerlendirme (#20) arayüzden doğrudan `POST /practice/{id}/answer` ile. Sonra aynı sözleşmeyle: kare açıklama
  (M3), seslendirme (M4), interaktif materyal (M5).
- **Köken politikası:** "Bilginin nereden geldiğini asla saklamaz." Her blok `provenance` taşır: `course`
  (alıntılı, doğrulanmış), `general` (ders materyalinde yok; alıntısız, her zaman etiketli), `none`
  (netleştirme, bilgilendirme). Durumlar:

  | Durum | Örnek | Davranış |
  |---|---|---|
  | Materyalde var ama arama bulamadı | Türkçe soru, İngilizce not | Ret değil arama hatası; retrieval'da düzeltilir |
  | Kaynağın farklı anlatımı | "Daha basit anlat", "örnekle göster" | `answer_from_course` (kaynaklı) |
  | Alan içi ön bilgi, materyalde yok | "log n nedir" | `explain_general`: "genel bilgi" etiketi, alıntısız; eğitmene materyal boşluğu olarak yansır |
  | Genel bilgi dersle çelişiyor | Ders 1'den indeksliyor | Ders kazanır; açıklama dersin parçalarıyla çelişmemeli |
  | Alan dışı, not verilen iş | "Tatil öner", ödev cevabı | `reply_notice` |

- **Kodda zorlanan kurallar:** `explain_general` yalnızca aynı turda `answer_from_course` "not_covered"
  döndürdüyse çalışır; turu bitiren araçlardan sonra araç çalışmaz; adım sınırı (`TUTOR_MAX_STEPS`); orkestratör
  hata verirse ya da içerik üretmeden biterse sabit akış (kaynaklı cevap → gerekirse genel açıklama).
- **Genel bilgi varsayılan kapalı** (`TUTOR_GENERAL_KNOWLEDGE=false`): bağımsız doğrulama (#10) gelene kadar
  bloklar `check="unchecked"` taşır. Açılması eğitmen ve ekip kararıdır; ders başına ayar sonraki adım.
- **FR-07:** Orkestratör task router'ın yerini alır; açık soru 4 bu kararla kapanır.
- **Değerlendirme:** Araçlar orkestratörsüz çağrılabilir (`/ask` aynı hat), dört koşullu ölçüm aynen sürer.
  Orkestratör için ayrı bir yönlendirme seti gerekir (mesaj → beklenen araç). 30 kapsam dışı soru ikiye ayrılır:
  alan dışı (ret beklenir) ve alan içi ama materyalde yok (etiketli genel açıklama beklenir). Genel açıklamaların
  doğruluğu ayrıca ölçülür; ölçülmezse hallucination "genel bilgi" kutusuna saklanmış olur.

**Model sağlayıcısı: Gemini Developer API, doğrudan** (OpenRouter aracı yok; ADR-5'teki "ikinci taraf" kalkar).
Fiyatlar ücretli katman, USD / 1M token, 2026-10-20'de [resmi sayfadan](https://ai.google.dev/gemini-api/docs/pricing):

| Görev | Model | Düşünme | Girdi / çıktı | Gerekçe |
|---|---|---|---|---|
| Orkestratör | `gemini-3.5-flash-lite` | minimal | 0,30 / 2,50 | Google'ın yüksek hacimli ajan alt görevleri için önerdiği stable model |
| Üretici (cevap, genel açıklama; sonra pratik, değerlendirme) | `gemini-3.8-flash` | low | 0,75 / 3,75 (duyurulan artış: 1,50 / 7,50) | Yeni projeler için önerilen stable Flash; function calling, structured output, caching, batch |
| Judge (#10, #13) | Gemini dışı aile (ör. Claude, OpenRouter üzerinden) | — | — | Generator'la aynı aile reddedilir (ANALYSIS §7.3) |

Pro sınıfı (`gemini-4-argon`, 2,00 / 10,00; 1 Aralık 2026'dan itibaren 4,00 / 20,00) yalnızca ölçüm gerektirirse.
Düşünme token'ları çıktı olarak ücretlenir; seviye görev başına ayarlanır.

- **Tahmini maliyet** (ölçülmedi; her tur `trace.usage` ile kaydediliyor): bir tur ≈ 2 orkestratör çağrısı
  (~$0,002) + 1 üretici çağrısı (~$0,006) ≈ **$0,008** (artıştan sonra ~$0,014). 20 öğrenci × 50 soru ≈ $8–14.
  Tam değerlendirme koşusu (180 soru × 4 koşul, orkestratörsüz) ≈ $4; Batch API ile yarısı.
- **Kota:** Model başına RPM/TPM/RPD yalnızca AI Studio'da görünür. Ücretsiz katman geliştirme içindir. Tier 1
  (faturalandırma bağlı) pilot için yeter; 10 dakikalık harcama sınırı $10. 429 ve 5xx SDK içinde üstel
  beklemeyle yeniden denenir.
- **Veri:** Ücretsiz katmanda gönderilen içerik Google ürünlerini geliştirmede kullanılabilir ve insan
  incelemesine açıktır: **kişisel veri ve onaysız ders materyali gönderilmez**; geliştirme herkese açık materyal
  (ör. MIT OCW) ve sentetik sorularla yapılır. Ücretli katmanda içerik eğitimde kullanılmaz; kötüye kullanım
  denetimi için sınırlı süre kaydedilir ve herhangi bir ülkede işlenebilir (yurt dışına aktarım: ADR-4). Gemini
  API koşulları kullanıcıların 18 yaşından büyük olmasını ister. **Pilot ücretli katmanla başlar.**

**İlk ölçüm (MIT 6.006, 89 doküman / 860 parça, gerçek Gemini; gold set değil, geliştirme seti).** 8 mesajlık
deneme setinde (5 Türkçe konu sorusu, alan dışı, selamlaşma, pratik isteği) ilk sürüm 5/8 doğru davrandı; şu üç
düzeltmeyle 8/8:
1. Türkçe soru İngilizce notta kelime eşleşmesi bulamıyordu: orkestratör materyalin dilinde doğal bir arama sorusu
   (`search_query`) yazıyor (anahtar kelime listesi belirgin biçimde daha kötü buldu).
2. Belirleyici parça ilk 5'in dışındaydı: 20 adayda hızlı modelle yeniden sıralama.
3. Gemini birden fazla kaynağı `[S1, S2]` diye yazıyordu; doğrulayıcı bunu alıntısız sayıp doğru cevapları
   reddediyordu: doğrulayıcı düzeltildi. Ayrıca kısmi cevap: materyalde olan kısım alıntılı, olmayan kısım ayrı not.
Tur maliyeti ~$0,005–0,008, süre 6–13 sn. Pratik sorusu ilk sürümde ~$0,01 ve 14–22 sn sürüyordu; "beni test et"
son cevabın kaynaklarından sorunca ve açık uçlu eşdeğerlik kontrolü hızlı modele geçince ~$0,003–0,004 ve ~9 sn.
Bu sayılar kalite iddiası değildir; ölçüm gold set ve insan etiketleriyle yapılır (#8, #13).

**Cevap biçimi ve iddia görünümü.** Çalışma alanı (#79) cevabı cümle cümle gösterir: ilk cümle başlık, kalanlar
kaynağına tıklanabilen numaralı iddialar. Gemini sık sık "…şu şekilde açıklanabilir:" girişi ve madde listesi
yazıyordu; liste içeren cevap bu görünümden düz metne düşüyordu. Cevap istemi düz, tek bilgili, etiketle biten
cümleler ister ve ilk cümlenin soruyu doğrudan cevaplamasını söyler; model yine liste yazarsa her madde ayrı iddia
olur. Kod ve tablo içeren cevaplar düz metin kalır. Rozet "N/N iddia kaynağa bağlı" der, "doğrulandı" demez:
doğrulayıcı her cümlenin geçerli bir kaynağa bağlandığını denetler, anlamca karşılaştırmaz (judge: #10).

**Rol ve model** (hepsi `LLM_*` ile değiştirilebilir): orkestratör ve yeniden sıralayıcı `gemini-3.5-flash-lite`
(minimal), üretici `gemini-3.8-flash` (low), pratik kontrolcüsü üreticiyle aynı model ama ayrı çağrı ve anahtarsız
bağlam (`LLM_CHECKER_*`). İddia judge'ı (#10) bundan ayrıdır ve farklı aile olmalıdır.

**Sonuçları.** `llm/gemini.py`, `llm/catalog.py` (fiyat, düşünme seviyeleri), rol bazlı `llm/gateway.py`;
`app/tutor/` (orkestratör, araçlar, kayıt); `POST /tutor/turn` ve `/tutor/turn/stream` (CONTRACTS.md §9).
Arayüzde bloklar çalışma alanının içinde gösterilir (`features/tutor/turns.ts`, `TutorTurnView.tsx`).
Açık: orkestratör yönlendirme seti, judge (#10), genel bilgi için eğitmen kararı, ücretli katman kaydı.

**Durum:** Önerildi · **Karar tarihi:** — · **Katılanlar:** Mehmet Akif Kurt (@saintpeterslibiri, öneren)

---

## Açık sorular

Bunlar ekip ya da dış taraf (eğitmen, bölüm) cevabı bekleyen konulardır. Cevaplanana kadar varsayım yapılmaz.

| # | Soru | Kim cevaplar | Etkilediği iş |
|---|---|---|---|
| 1 | **Video barındırma.** Videolar nerede (LMS, YouTube, dosya)? Henüz bilinmiyor; eğitmenle konuşulacak (#8, materyal envanteri). `media_url` barındırma yönteminden bağımsız tasarlandı (CONTRACTS.md §4); yöntem belli olunca yalnızca URL üretimi ve oynatıcı bileşeni etkilenir. | Eğitmen / #8 | FR-06, FR-18 video; CONTRACTS.md §4 (metin donduruldu, koda geçişi bu karara bağlı) |
| 2 | **Ders kitabı telifi.** Hangi kitap bölümleri indekslenebilir ve hosted modele gönderilebilir? | Eğitmen / bölüm | ADR-3, ADR-5, WP1 |
| 3 | **Saklama süresinin kesin tarihi.** Sohbet, öğrenme kaydı ve eval verisi ne zaman silinecek veya anonimleştirilecek? | Ekip + bölüm/etik kurul | ADR-4 |
| 4 | **FR-07 (task router).** Görev başına ayrı endpoint'ler (`/ask`, `/practice`, `/practice/{id}/answer`) FR-07'yi karşılamış sayılır mı? Sayılmazsa `routing/router.py` gerçekleştirilmeli. **Öneri: ADR-7** (orkestratör task router'ın yerini alır). | Ekip | FR-07 kabul kanıtı |
| 5 | **[Kapandı, #11]** Endpoint'ler artık oturum ve ders üyeliği ister; üye olmayana 404, rolü yetmeyene 403 (CONTRACTS.md §3). Eski kayıt: **Kaynak ve doküman endpoint'lerinin dersle sınırlı olmaması — güvenlik açığı, #11'de kapatılmalı.** `GET /sources/{source_id}`, `GET /documents/{id}/chunks`, `/documents/{id}/file`, `/documents/{id}/pages/{n}.png` ve `DELETE /documents/{id}` ders üyeliği kontrol etmiyor; chunk/doküman kimliğini bilen herkes herhangi bir dersin içeriğini okuyabilir (silme dahil). Ayrıca `POST /courses/{id}/materials`, `GET /courses/{id}/materials` ve `POST /courses` kimlik doğrulamasız. PR #68 ile iki endpoint daha eklendi ve bunlar da kimliksiz: `PATCH /courses/{id}` (herkes herhangi bir dersin bilgisini değiştirebilir) ve `GET /instructor/courses/{id}/activity` (herkes herhangi bir dersin öğrenci soru metinlerini görebilir). Aynı şekilde, sohbetler (`conversation_id`) bir kullanıcıya bağlı olmadığı için kimliği bilinen sohbet okunabilir. | #11 | FR-04, FR-10, FR-17 |
| 6 | **Judge modeli ve hosted sağlayıcı ayarları.** Hangi model ailesi, hangi sağlayıcı ve veri saklama ayarları? ADR-7 önerisiyle üretici Gemini; judge Gemini dışı bir aile olmalı. | Ekip | ADR-5, FR-14 |
| 7 | **Ana sayfa yönlendirmesi.** Hem eğitmen hem öğrenci üyeliği olan kullanıcı hangi ana sayfaya gider? (Öneri: en az bir derste eğitmense eğitmen ana sayfası, derste rol değiştirme bağlantısıyla.) | Ekip (Product) | #12 |
