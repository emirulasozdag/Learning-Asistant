import { Code2, ListChecks, PenLine, type LucideIcon } from "lucide-react";

import type { Difficulty, PracticeType } from "../../api/types";

export const TYPE_LABEL: Record<PracticeType, string> = {
  mcq: "Çoktan seçmeli",
  short_answer: "Kısa cevap",
  code_tracing: "Kod izleme",
};

/** Soru türünün öğrenciye ne yaptıracağı (kurulum ekranındaki kartlar). */
export const TYPE_DETAILS: Record<PracticeType, { description: string; icon: LucideIcon }> = {
  mcq: { description: "Dört şıktan doğrusunu seç; hızlı tekrar için.", icon: ListChecks },
  short_answer: { description: "Kendi cümlelerinle açıkla; rubrikle puanlanır.", icon: PenLine },
  code_tracing: { description: "Kodun çıktısını ya da adımlarını bul.", icon: Code2 },
};

export const DIFFICULTY_LABEL: Record<Difficulty, string> = { easy: "Kolay", medium: "Orta", hard: "Zor" };

/** Şık harfi: 0 → "A". */
export function optionLetter(index: number): string {
  return String.fromCharCode(65 + index);
}

export function formatScore(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(".", ",");
}

/** Değerlendiriciden "eksik_kavram" biçiminde gelebilen kavram adını okunur yapar. */
export function conceptLabel(concept: string): string {
  return concept.replace(/_/g, " ");
}

export type ResultTone = "success" | "warning" | "danger";

/** Puanın sonucu: tam, kısmi ya da hiç. */
export function resultOf(score: number, maxScore: number): { tone: ResultTone; label: string } {
  if (score >= maxScore) return { tone: "success", label: "Doğru" };
  if (score <= 0) return { tone: "danger", label: "Doğru değil" };
  return { tone: "warning", label: "Kısmen doğru" };
}
