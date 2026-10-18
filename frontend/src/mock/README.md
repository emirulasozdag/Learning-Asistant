# mock/

Backend'i henüz olmayan alanlar için gerçekçi örnek veri. **Bileşenler bu klasörü doğrudan
içe aktarmaz**; yalnızca `src/services/` aktarır. Gerçek API hazır olunca ilgili servis
fonksiyonunun içi değişir, ekranlara dokunulmaz.

| Dosya | Kullanan servis | Gerçek API gelince |
|---|---|---|
| `users.ts` | `authService` | Kimlik doğrulama (FR-17) |
| `courseStats.ts` | `courseService` | Öğrenci sayısı, soru sayısı (öğrenme kaydı, FR-15) |
| `dashboard.ts` | `dashboardService` | Eğitmen/öğrenci özetleri |
| `practice.ts` | `practiceService` | Pratik üretimi ve değerlendirme (FR-11–13) |
| `tutor.ts` | `tutorService` | Ders başına önerilen sorular |
