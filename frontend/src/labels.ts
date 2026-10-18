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
