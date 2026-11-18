# Arayüz: tasarım sistemi ve ekranlar

> **Güncelleme (#103, #106):** Uygulamada tek bir çerçeve var: üst bar (kurum + ürün), konum şeridi ve ders
> sayfalarında ortak ders çerçevesi (`CourseShell`: ders şeridi, sol ders menüsü, içerik). AI Tutor da bu çerçevenin
> içinde açılır; ayrı "çalışma alanı" kabuğu (`StudioShell`) kaldırıldı. Mock veri yoktur; her ekran gerçek API'yi kullanır.
> Eski görev listesi (A–D) tamamlandı ya da gerçek ekranlarla değiştirildi; güncel ekran listesi bölüm 2'de.

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

**Veri:** Bileşenler API'yi doğrudan çağırmaz; `src/services/` üzerinden okur (`api/client.ts` → servis → sayfa).

**Tutarlılık kuralları (#103, #106):**
- Ders bölümlerinin adları tek yerde: `features/courses/sections.ts` (menü, sekmeler ve konum şeridi aynı listeden okur).
- Sayfada tek `h1`: bölüm sayfasının başlığı (`PageTitle`); aynı sayfadaki diğer başlıklar `PageTitle level={2}` ya da `SectionHeader`. Ders adı şerittir, başlık değildir.
- Terimler: "doküman" (belge değil), "video" (ders videosu ve transkripti), "Beni bu konuda test et".
- Geri alınamaz işlem pencerelerinde ilk odak "Vazgeç"tedir.
- Sabit renk yok (`text-white`, `fill="white"` gibi); tema değişkenleri kullanılır. Tema seçici Hesabım sayfasındadır.

**Kontrol:** Bir PR'dan önce `npm run lint && npm run build` çalıştırın, ekranı hem masaüstünde hem 375px genişlikte kontrol edin.

## 2. Ekranlar

| Rol | Adres | Sayfa |
|---|---|---|
| Her ikisi | `/{rol}/account` | `pages/account/AccountPage.tsx`: araştırma kaydı, tema, verilerimi/hesabımı sil |
| Öğrenci | `/student` | `pages/student/StudentDashboard.tsx` |
| Öğrenci | `/student/courses/:id/tutor` | `pages/student/TutorPage.tsx` (ders çerçevesinde; `?video=&t=` ile ders videosu) |
| Öğrenci | `/student/courses/:id/learning` | `pages/student/LearningRecordPage.tsx` |
| Eğitmen | `/instructor` | `pages/instructor/InstructorDashboard.tsx` |
| Eğitmen | `/instructor/courses/:id/materials` | `pages/instructor/MaterialsPage.tsx` |
| Eğitmen | `/instructor/courses/:id/activity` | `pages/instructor/CourseActivityPage.tsx` (cevabı onayla/düzelt) |
| Eğitmen | `/instructor/courses/:id/review` | `pages/instructor/CourseReviewPage.tsx` (sık hatalar, pratik soruları) |
| Her ikisi | `…/courses/:id/{syllabus,calendar,videos,lecture-notes,…}` | `pages/course/*` |

Ctrl/⌘+K materyal araması (öğrenci) her ders sayfasında açılır (`features/studio/StudioProvider.tsx`).

## 3. Klasör haritası

```
src/
├── ui/          tasarım sistemi bileşenleri (yalnızca görünüm; veri bilmez)
├── layouts/     AppShell (üst bar + konum şeridi), CourseShell (ders çerçevesi), AuthLayout
├── auth/        oturum (AuthProvider, useAuth, RequireRole)
├── services/    veri katmanı (gerçek API)
├── features/    ekranlara özel bileşenler (tutor/, video/, studio/, materials/, courses/, instructor/)
├── pages/       route başına sayfa
└── router.tsx   tüm adresler
```
