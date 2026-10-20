const SCORE = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const SECONDS = new Intl.NumberFormat("tr-TR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Benzerlik skoru: 0,91 */
export function formatScore(value: number): string {
  return SCORE.format(value);
}

/** Cevap süresi: 1,8 sn; çok kısa sürelerde "0,1 sn altı". */
export function formatSeconds(milliseconds: number): string {
  if (milliseconds < 100) return `${SECONDS.format(0.1)} sn altı`;
  return `${SECONDS.format(milliseconds / 1000)} sn`;
}
