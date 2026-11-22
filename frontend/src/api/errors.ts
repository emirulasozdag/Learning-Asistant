import { ApiError } from "./client";

/**
 * Hatanın öğrenciye/eğitmene gösterilecek metni. Backend'in `detail` metni zaten Türkçe ve
 * açıklayıcıdır (ör. "E-posta veya şifre hatalı."); ağ, akış ve sunucu hatalarında ise tarayıcının
 * teknik metni ("Failed to fetch") yerine ne olduğunu ve ne yapılacağını söyleyen bir cümle döner.
 */
export function userMessage(reason: unknown, fallback = "Bir sorun oluştu. Tekrar dene."): string {
  if (reason instanceof ApiError) {
    if (reason.kind === "network") return "Sunucuya ulaşılamadı. Bağlantını kontrol edip tekrar dene.";
    if (reason.kind === "stream") return "Cevap yarıda kesildi. Tekrar dene.";
    if (reason.status !== undefined && reason.status >= 500) {
      return "Sunucuda geçici bir sorun oluştu. Biraz sonra tekrar dene.";
    }
    return reason.message || fallback;
  }
  // Servislerin kullanıcı için ürettiği hatalar (ör. AuthError: "E-posta veya şifre hatalı.")
  // olduğu gibi gösterilir; programlama hataları (TypeError vb.) gösterilmez.
  if (reason instanceof Error && !(reason instanceof TypeError) && !(reason instanceof SyntaxError) && reason.message) {
    return reason.message;
  }
  return fallback;
}
