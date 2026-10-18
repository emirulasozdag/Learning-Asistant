/** Ders başına henüz backend'i olmayan sayılar. Anahtar: ders kodu. */
export interface CourseStats {
  students: number;
  questionsAsked: number;
  term: string;
}

export const COURSE_STATS: Record<string, CourseStats> = {
  BLM2512: { students: 86, questionsAsked: 412, term: "Güz 2026" },
  BLM3021: { students: 54, questionsAsked: 167, term: "Güz 2026" },
};

export const DEFAULT_COURSE_STATS: CourseStats = { students: 0, questionsAsked: 0, term: "Güz 2026" };
