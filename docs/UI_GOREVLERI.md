# Arayüz: tasarım sistemi ve ekip görevleri

> **Güncelleme:** Ürün sürümünde mock veriler ve "geliştiriliyor" sayfaları kaldırıldı (plan
> kuralı #6). Görev A ve C gerçek materyal verisiyle yapıldı. Görev B ve D'nin sayfaları,
> route'ları ve mock dosyaları silindi. Bu ekranlar, backend API'leri hazır olunca ilgili sprint
> issue'larıyla (#12, #17, #22…) gerçek veriyle eklenecek. Aşağıdaki görev listesi geçmiş kayıt
> olarak duruyor; tasarım kuralları (bölüm 1) geçerli.

Uygulamanın ilk profesyonel sürümünde tasarım sistemi, iskelet, giriş/kayıt, **AI Tutor** ve
**Materyaller** ekranları hazır. Aşağıdaki dört ekran ekibe kaldı. Her biri için sayfa dosyası,
route'u ve mock verisi hazır; yeni bir şey kurmanıza gerek yok, yalnızca sayfanın içini doldurun.

## 1. Tasarım sistemi — kurallar

**Karakter:** akademik, güvenilir, sade. Bir üniversite ürünü gibi; oyuncak ya da admin şablonu gibi değil.

| Konu | Kural |
|---|---|
| Renk | Nötr zemin (`canvas`), beyaz yüzey (`surface`), koyu metin (`ink`). Tek vurgu rengi: `accent` (mavi). Sarı `marker` **yalnızca** "ders materyalinden alıntı" anlamında kullanılır. `success` / `warning` / `danger` yalnızca durum bildirir. |
| Yazı | Arayüz: IBM Plex Sans. Ders metni ve alıntılar: Source Serif (`font-serif`). Ölçek: `text-xs` 12 · `sm` 13 · `base` 14 · `md` 15 · `lg` 18 · `xl` 22 · `2xl` 28 · `3xl` 40. Sayfa başlığı `text-2xl font-semibold tracking-tight`. |
| Boşluk | 4px tabanlı. Sayfa kenarı `px-6 lg:px-10`, sayfa üstü `pt-8`, bölümler arası `mt-10`. |
| Köşe / gölge | Kontroller `rounded-control` (6px), paneller `rounded-panel` (8px). Gölge yalnızca yüzen katmanlarda (`shadow-float`: menü, diyalog, çekmece). |
| Kart | Her şeyi karta koymayın. Liste için `divide-y` + tek çerçeve; tablo için `ui/Table`. |
| İkon | Yalnızca `lucide-react`, 14–16px. Emoji yok. |
| Metin | Türkçe, kullanıcının dili ("indeksleme" değil "bilgi tabanına eklendi"). Büyük harfli etiket ve "→" süsü yok. |
| Durumlar | Her veri bölümünde: yükleniyor (`ui/Skeleton`), boş (`ui/EmptyState`), hata (`EmptyState tone="danger"`). |

**Hazır bileşenler (`src/ui/`)**

- **Temel:** `Button` (+ `buttonStyles`), `IconButton`, `Field`, `Badge` / `StatusBadge`, `SegmentedControl`
- **Navigasyon ve düzen:** `RouteTabs`, `PageHeader` / `SectionHeader`
- **Veri:** `Table` (`TH`, `TR`, `TD`), `Skeleton` / `SkeletonRows`, `EmptyState`
- **Katmanlar:** `Dialog`, `Drawer`
- **Diğer:** `Avatar`, `FileBadge`, `Logo`

**Veri:** Bileşenler `src/mock/` dosyalarını **doğrudan içe aktarmaz**; her zaman `src/services/` üzerinden okur. Backend hazır olunca yalnızca servis fonksiyonunun içi değişir.

**Kontrol:** Bir PR'dan önce `npm run lint && npm run build` çalıştırın, ekranı hem masaüstünde hem 375px genişlikte kontrol edin.

## 2. Görevler

### Görev A — Eğitmen ana sayfası
- **Dosya:** `src/pages/instructor/InstructorDashboard.tsx` (karşılama ve "Derslerim" hazır)
- **Veri:** `dashboardService.instructorSummary()` (mock: `src/mock/dashboard.ts`)
- **Eklenecekler:**
  - Karşılamanın altına sade bir özet satırı: Dersler · Öğrenciler · Sorulan sorular · Pratik oturumları (4 sayı, kartsız, ince ayraçlarla).
  - "Bu hafta en çok sorulan konular" listesi: konu, soru sayısı, ilgili derse bağlantı.
  - Ders satırına materyal sayısı (`courseService.materials(id)`).
- **Grafik eklemeyin**; sayılar ve listeler yeterli.
- **Bitti:** Yükleniyor / boş / hata durumları var, 375px'te düzgün.

### Görev B — Ders sayfası sekmeleri (Genel bakış, Öğrenciler, Analitik)
- **Dosya:** `src/pages/instructor/CourseSections.tsx` (şu an "geliştiriliyor" yer tutucuları)
- **Genel bakış:**
  - İçerik: materyal özeti (doküman / sayfa / parça), son öğrenci soruları, "materyalde bulunamayan" sorular. Bu sonuncusu eğitmen için en değerli bilgi: hangi konuyu eklemesi gerektiğini gösterir.
  - Bittiğinde `src/router.tsx` içindeki ders `index` yönlendirmesini `materials` yerine `overview` yapın ve `CourseLayout`'taki `upcoming` işaretini kaldırın.
- **Öğrenciler:** `ui/Table` ile öğrenci, soru sayısı, son etkinlik.
- **Analitik:** sık hatalar ve kullanılan kaynaklar (FR-16).
- **Veri:** yeni mock dosyası + servis fonksiyonu. Gerçek kaynak `messages` tablosu (`meta.declined`, `meta.cited_source_ids`).

### Görev C — Öğrenci ana sayfası
- **Dosya:** `src/pages/student/StudentDashboard.tsx` (karşılama ve "Derslerim" hazır)
- **Veri:** `dashboardService.recentQuestions()`, `practiceProgress()`
- **Eklenecekler:**
  - "Kaldığın yerden devam et": son sorulan soru ve dersi, AI Tutor'a dönüş bağlantısı.
  - "Son sorular" listesi.
  - "Pratik ilerlemesi": ders başına tamamlanan, ortalama puan, zayıf konu ve "Bu konuyu çalış" bağlantısı.
- **Not:** Eğitmen ana sayfasının kopyası olmasın; odak "öğrenmeye devam etmek".

### Görev D — Pratik çalışma alanı
- **Dosya:** `src/pages/student/PracticePage.tsx`. AI Tutor'daki "Bu konuyu çalış" buraya `?course=&topic=` ile gelir.
- **Veri:** `practiceService.nextQuestion()` / `submit()` (mock: `src/mock/practice.ts`)
- **Soru durumu:** temiz bir çalışma alanı (soru kartı değil):
  - soru metni
  - zorluk
  - kaynak (`Notlar, sayfa 2`; tıklanınca kaynak açılsın; AI Tutor'daki `features/tutor/SourcePanel` yeniden kullanılabilir)
  - cevap alanı ve "Gönder"
- **Geri bildirim durumu:**
  - Puan (`8/10`)
  - Anladıkların
  - Eksik kavram
  - Açıklama
  - Kaynak
  - "Bu eksik üzerine çalış" (yeni soru)
- **Gerçek API:** `POST /practice`, `POST /practice/{id}/answer` (backend'de şu an 501; FR-11–13).

## 3. Klasör haritası

```
src/
├── ui/          tasarım sistemi bileşenleri (yalnızca görünüm; veri bilmez)
├── layouts/     AppShell (sidebar + topbar), AuthLayout, menü tanımları
├── auth/        oturum (AuthProvider, useAuth, RequireRole)
├── services/    veri katmanı: gerçek API + mock
├── mock/        örnek veri (yalnızca services/ kullanır)
├── features/    ekranlara özel bileşenler (tutor/, materials/, courses/)
├── pages/       route başına sayfa
└── router.tsx   tüm adresler
```
