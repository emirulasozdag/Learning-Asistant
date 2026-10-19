import type { Citation, MaterialType } from "./api/types";

export const MATERIAL_LABELS: Record<MaterialType, string> = {
  notes: "Ders notu",
  slides: "Slayt",
  textbook: "Ders kitabı",
  past_exam: "Geçmiş sınav",
  transcript: "Transkript",
  video: "Video",
};

/** Yükleme ekranında seçilebilen türler (transkript ve video sonraki adımda). */
export const UPLOADABLE_TYPES: MaterialType[] = ["notes", "slides", "textbook", "past_exam"];

export function materialLabel(type: string): string {
  return MATERIAL_LABELS[type as MaterialType] ?? type;
}

const LANGUAGE_LABELS: Record<string, string> = { tr: "Türkçe", en: "İngilizce" };

/** Dersin materyal dili: "tr" → "Türkçe". */
export function languageLabel(code: string): string {
  return LANGUAGE_LABELS[code] ?? code.toUpperCase();
}

export function citationLabel(citation: Citation): string {
  const title = citation.document_title ?? "Kaynak";
  return citation.page ? `${title}, s. ${citation.page}` : title;
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
