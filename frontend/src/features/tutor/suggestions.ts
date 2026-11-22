import type { DocumentOut, MaterialType } from "../../api/types";
import { sortByTitle } from "../materials/sortByTitle";

export interface Suggestion {
  kind: "explain" | "quiz";
  text: string;
}

// Konu başlığı çıkarılacak türler (öncelik sırasıyla); ödev ve çözümler konu kaynağı değildir.
// Ders notu olmayan derste (ör. 18.06) konular ders videolarının başlıklarındadır (#32).
const TOPIC_TYPES: MaterialType[] = ["notes", "slides", "textbook", "transcript", "video"];

/**
 * Boş sohbette önerilen sorular: dersin kendi materyal başlıklarından (uydurma örnek yok).
 * "Lecture 13: Dijkstra's Algorithm" → "Dijkstra's Algorithm". Konular dersin başından
 * sonuna yayılarak seçilir; ikisi "anlat", ikisi "beni test et".
 */
export function courseSuggestions(documents: DocumentOut[], count = 4): Suggestion[] {
  return courseTopics(documents, count).map((topic, index) =>
    index % 2 === 0
      ? { kind: "explain", text: `${topic} konusunu kısaca anlatır mısın?` }
      : { kind: "quiz", text: `${topic} konusunda beni test et` },
  );
}

/**
 * Dersin materyal başlıklarından konu adları ("Lecture 13: Dijkstra's Algorithm" → "Dijkstra's
 * Algorithm"); dersin başından sonuna yayılarak en fazla `count` tane. Uydurma konu yoktur.
 */
export function courseTopics(documents: DocumentOut[], count: number): string[] {
  // Konu çıkan ilk tür kullanılır: kitap başlıkları ("Linear Algebra textbook") konu taşımazsa
  // sıradaki türe geçilir.
  for (const type of TOPIC_TYPES) {
    const topics = [
      ...new Set(
        sortByTitle(documents.filter((d) => d.material_type === type))
          .map((d) => topicOf(d.title))
          .filter((topic): topic is string => topic !== null),
      ),
    ];
    if (topics.length > 0) return spread(topics, count);
  }
  return [];
}

// Konu taşımayan başlıklar: "Recitation 5", "Lecture 3", "Hafta 2", "Giriş", sınav tekrarı
// ("Quiz 2 review", "Final course review", "Exam 1 review").
const NO_TOPIC =
  /^(recitation|lecture|week|hafta|ders|bölüm|chapter|unit)\s*\d*$|^(introduction|intro|giriş)$|^(quiz|exam|midterm|final)(\s+\d+|\s+course|\s+exam)?\s+review$/i;

/**
 * "Lecture 4: Hashing" → "Hashing"; "Hafta 3 – Sıralama" → "Sıralama";
 * "Lecture 6: Binary Trees, Part 1" → "Binary Trees". Konu ayrılmamış başlık ("Ders notları",
 * "Recitation 5") öneri olmaz: null.
 */
function topicOf(title: string): string | null {
  const parts = title.split(/\s*[:–—]\s*|\s+-\s+/);
  if (parts.length < 2) return null;
  const topic = parts
    .slice(1)
    .join(": ")
    .replace(/,?\s*(part|kısım|bölüm)\s*([ivx]+|\d+)$/i, "")
    .replace(/\s+([ivx]+|\d+)$/i, "")
    .trim();
  return topic.length >= 3 && !NO_TOPIC.test(topic) ? topic : null;
}

/** Listenin başından sonuna eşit aralıklı `count` öğe. */
function spread<T>(items: T[], count: number): T[] {
  if (items.length <= count) return items;
  const step = items.length / count;
  return Array.from({ length: count }, (_, index) => items[Math.floor(index * step + step / 2)]);
}
