/**
 * PDF'ten gelen metinde satır sonları sayfadaki kırılımlardır. Okurken paragraf içindeki
 * satırları birleştirir; paragraf aralarını, madde ve numaralı satırları korur.
 */
export function reflow(text: string): string {
  return text
    .split(/\n{2,}/)
    .map((paragraph) =>
      paragraph
        .split("\n")
        .reduce((joined, line, index) => {
          if (index === 0) return line;
          const startsItem = /^\s*([-•*–]|\d+[.)])\s/.test(line);
          return startsItem ? `${joined}\n${line}` : `${joined} ${line.trimStart()}`;
        }, ""),
    )
    .join("\n\n");
}

const RELATIVE = new Intl.RelativeTimeFormat("tr", { numeric: "auto" });
const SHORT_DATE = new Intl.DateTimeFormat("tr", { day: "numeric", month: "short" });

/** "az önce", "5 dakika önce", "dün", "12 Eki" */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 60) return "az önce";
  if (abs < 3600) return RELATIVE.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return RELATIVE.format(Math.round(seconds / 3600), "hour");
  if (abs < 7 * 86400) return RELATIVE.format(Math.round(seconds / 86400), "day");
  return SHORT_DATE.format(date);
}

/** Saate göre selamlama. */
export function greeting(now: Date = new Date()): string {
  const hour = now.getHours();
  if (hour < 6) return "İyi geceler";
  if (hour < 12) return "Günaydın";
  if (hour < 18) return "İyi günler";
  return "İyi akşamlar";
}

/** Saniye → "m:ss" (bir saat ve üstü için "h:mm:ss"): videoda konum göstermek için. */
export function formatTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${secs}` : `${minutes}:${secs}`;
}

/** Video parçasının aralığı: "12:34–13:20" (bitiş yoksa yalnızca başlangıç). */
export function formatTimeRange(start: number, end: number | null | undefined): string {
  return end == null ? formatTime(start) : `${formatTime(start)}–${formatTime(end)}`;
}
