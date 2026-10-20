import type { Citation, DocumentOut, MaterialType } from "./api/types";
import { formatTime } from "./text";
import type { IndexStatus } from "./ui/Badge";

export const MATERIAL_LABELS: Record<MaterialType, string> = {
  notes: "Ders notu",
  slides: "Slayt",
  textbook: "Ders kitabı",
  past_exam: "Geçmiş sınav",
  assignment: "Ödev",
  practice_problem: "Pratik problem",
  transcript: "Transkript",
  video: "Video",
};

/** Yükleme ekranında seçilebilen türler (video: altyazı dosyası; videonun kendisi henüz yüklenemez). */
export const UPLOADABLE_TYPES: MaterialType[] = [
  "notes",
  "slides",
  "textbook",
  "past_exam",
  "assignment",
  "practice_problem",
  "video",
];

/** Türlerin listelenme sırası (genel bakış, tüm materyaller). */
export const TYPE_ORDER: MaterialType[] = [
  "notes",
  "slides",
  "textbook",
  "past_exam",
  "practice_problem",
  "assignment",
  "transcript",
  "video",
];

export function materialLabel(type: string): string {
  return MATERIAL_LABELS[type as MaterialType] ?? type;
}

/** Dokümanın boyutu: sayfa tabanlı dosyada sayfa sayısı, videoda süre. */
/** Dokümanın işlem durumunu rozet durumuna çevirir. */
export function documentIndexStatus(document: DocumentOut): IndexStatus {
  return document.status === "ready" ? "indexed" : document.status;
}

export function documentExtent(document: Pick<DocumentOut, "material_type" | "page_count" | "duration_s">): string {
  if (document.material_type === "video") {
    return document.duration_s == null ? "video" : formatTime(document.duration_s);
  }
  return `${document.page_count} sayfa`;
}

const LANGUAGE_LABELS: Record<string, string> = { tr: "Türkçe", en: "İngilizce" };

/** Dersin materyal dili: "tr" → "Türkçe". */
export function languageLabel(code: string): string {
  return LANGUAGE_LABELS[code] ?? code.toUpperCase();
}

export function citationLabel(citation: Citation): string {
  const title = citation.document_title ?? "Kaynak";
  if (citation.page) return `${title}, s. ${citation.page}`;
  return citation.t_start != null ? `${title}, ${formatTime(citation.t_start)}` : title;
}

const MINOR_WORDS = new Set(["ve", "ile", "and", "of", "the", "için"]);

/** Ders adının baş harfleri: "Veri Yapıları ve Algoritmalar" → "VY". */
export function courseInitials(name: string): string {
  const words = name.split(/\s+/).filter((word) => word && !MINOR_WORDS.has(word.toLocaleLowerCase("tr")));
  return words
    .slice(0, 2)
    .map((word) => word[0].toLocaleUpperCase("tr"))
    .join("");
}

export const LEVEL_LABELS: Record<"undergraduate" | "graduate", string> = {
  undergraduate: "Lisans",
  graduate: "Yüksek lisans",
};

/** Ders şeridindeki üst satır: "BLM2512 | Güz 2026 | Lisans" (yalnızca dolu alanlar). */
export function courseMetaParts(course: {
  code: string;
  term: string | null;
  level: "undergraduate" | "graduate" | null;
}): string[] {
  return [course.code, course.term, course.level && LEVEL_LABELS[course.level]].filter(
    (part): part is string => Boolean(part),
  );
}

export interface MaterialTotals {
  /** Yalnızca sayfa tabanlı dokümanların (video değil) sayfa toplamı. */
  pages: number;
  /** Video dokümanlarının toplam süresi (saniye). */
  videoSeconds: number;
  /** Sayfa tabanlı / video doküman var mı: yoksa ilgili sayaç hiç gösterilmez. */
  hasPages: boolean;
  hasVideo: boolean;
}

type TotalsInput = Pick<DocumentOut, "material_type" | "page_count" | "duration_s">;

/** Sayfa ve süre toplamları ayrı hesaplanır: video "0 sayfa" diye sayılmaz. */
export function materialTotals(documents: TotalsInput[]): MaterialTotals {
  const videos = documents.filter((d) => d.material_type === "video");
  const paged = documents.filter((d) => d.material_type !== "video");
  return {
    pages: paged.reduce((sum, d) => sum + d.page_count, 0),
    videoSeconds: videos.reduce((sum, d) => sum + (d.duration_s ?? 0), 0),
    hasPages: paged.length > 0,
    hasVideo: videos.length > 0,
  };
}

/** "12 sayfa", "video süresi 3:30" ya da ikisi birden; hiçbiri yoksa boş metin. */
export function describeTotals(totals: MaterialTotals): string {
  const parts: string[] = [];
  if (totals.hasPages) parts.push(`${totals.pages} sayfa`);
  if (totals.hasVideo) parts.push(`video süresi ${formatTime(totals.videoSeconds)}`);
  return parts.join(", ");
}

/** Tablo hücresi için kısa biçim: "12", "3:30" ya da "12 · 3:30". */
export function compactTotals(totals: MaterialTotals): string {
  const parts: string[] = [];
  if (totals.hasPages) parts.push(String(totals.pages));
  if (totals.hasVideo) parts.push(formatTime(totals.videoSeconds));
  return parts.length > 0 ? parts.join(" · ") : "—";
}

/** Sayfa/süre sütununun başlığı. */
export function totalsHeading(totals: MaterialTotals): string {
  return totals.hasVideo ? (totals.hasPages ? "Sayfa / süre" : "Süre") : "Sayfa";
}
