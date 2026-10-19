# mock/

Backend'i henüz olmayan tek alan: **kimlik doğrulama**. Bileşenler bu klasörü doğrudan içe
aktarmaz; yalnızca `src/services/authService.ts` aktarır.

| Dosya | Kullanan servis | Gerçek API gelince |
|---|---|---|
| `users.ts` | `authService` | Kimlik doğrulama (FR-17, S02 #12) |

Ekranlarda sahte sayı ya da sahte içerik gösterilmez (plan kuralı #6). Backend'i olmayan
özellikler (pratik, öğrenci listesi, analitik) API hazır olunca eklenir.
