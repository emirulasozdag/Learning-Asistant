import type { DocumentOut } from "../../api/types";

/** Başlığa göre doğal sıra: "Lecture 2" → "Lecture 10"dan önce. */
export function sortByTitle(documents: DocumentOut[]): DocumentOut[] {
  return [...documents].sort((a, b) =>
    a.title.localeCompare(b.title, "en", { numeric: true, sensitivity: "base" }),
  );
}
