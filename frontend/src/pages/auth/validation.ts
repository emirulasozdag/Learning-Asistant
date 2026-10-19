const EMAIL_SHAPE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
// E-posta adreslerinde ASCII dışı harf (ı, ş, ğ, ü, ö, ç…) çoğu sunucuda geçersizdir.
const NON_ASCII = /[^\x20-\x7e]/;

/** E-posta için Türkçe, ne yapılacağını söyleyen hata; geçerliyse null. */
export function emailError(email: string): string | null {
  const value = email.trim();
  if (!value) return "E-posta adresini yaz.";
  if (NON_ASCII.test(value)) {
    return "E-posta adresinde Türkçe karakter kullanılamaz (ı → i, ş → s, ğ → g, ü → u, ö → o, ç → c).";
  }
  if (!EMAIL_SHAPE.test(value)) return "Geçerli bir e-posta adresi yaz, ör. ad.soyad@universite.edu.tr";
  return null;
}
