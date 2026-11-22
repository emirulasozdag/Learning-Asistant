/**
 * Sekme oturumunda saklanan çalışma önbelleği (Tutor sohbeti, pratik oturumu) için ortak kurallar
 * (#134). Anahtar kullanıcıya bağlıdır: aynı tarayıcıda başka bir öğrenci giriş yapınca öncekinin
 * sohbeti ve pratiği okunmaz. Çıkışta, oturum düşünce (401) ve veriler silinince hepsi temizlenir.
 */
const PREFIXES = ["la.tutor.", "la.practice."];

/** Kullanıcıya bağlı anahtar; kullanıcı yoksa `null` (hiçbir şey okunmaz ve yazılmaz). */
export function studyCacheKey(prefix: "la.tutor." | "la.practice.", userId: number | null | undefined, rest: string): string | null {
  return userId == null ? null : `${prefix}u${userId}.${rest}`;
}

/** Bütün Tutor ve pratik önbelleğini siler (her kullanıcınınkini; eski biçimdeki anahtarlar dahil). */
export function clearStudyCache(): void {
  try {
    const keys: string[] = [];
    for (let index = 0; index < sessionStorage.length; index += 1) {
      const key = sessionStorage.key(index);
      if (key && PREFIXES.some((prefix) => key.startsWith(prefix))) keys.push(key);
    }
    keys.forEach((key) => sessionStorage.removeItem(key));
  } catch {
    // Depolama kapalı: silinecek bir şey yok.
  }
}
