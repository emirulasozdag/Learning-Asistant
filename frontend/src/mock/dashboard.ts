/**
 * Dashboard'lar için örnek veri (ekip görevi: docs/UI_GOREVLERI.md).
 * Gerçek kaynak: öğrenme kaydı (FR-15) ve soru logları (messages tablosu).
 */

export interface InstructorSummary {
  students: number;
  questionsAsked: number;
  practiceSessions: number;
  /** Son 7 günde öğrencilerin en çok sorduğu konular. */
  topTopics: { topic: string; questions: number }[];
}

export const INSTRUCTOR_SUMMARY: InstructorSummary = {
  students: 140,
  questionsAsked: 579,
  practiceSessions: 213,
  topTopics: [
    { topic: "İkili arama", questions: 64 },
    { topic: "Ağaç dolaşımları", questions: 41 },
    { topic: "Zaman karmaşıklığı", questions: 37 },
  ],
};

export interface RecentQuestion {
  id: string;
  courseCode: string;
  question: string;
  askedAt: string;
  sources: number;
}

export const STUDENT_RECENT_QUESTIONS: RecentQuestion[] = [
  {
    id: "q1",
    courseCode: "BLM2512",
    question: "Binary search neden sıralı bir dizi gerektirir?",
    askedAt: "2026-10-18T19:42:00Z",
    sources: 2,
  },
  {
    id: "q2",
    courseCode: "BLM2512",
    question: "İkili aramanın zaman karmaşıklığı nedir?",
    askedAt: "2026-10-18T19:47:00Z",
    sources: 1,
  },
  {
    id: "q3",
    courseCode: "BLM3021",
    question: "mid = (lo + hi) // 2 neden taşmaya yol açabilir?",
    askedAt: "2026-10-17T15:10:00Z",
    sources: 1,
  },
];

export interface PracticeProgress {
  courseCode: string;
  completed: number;
  averageScore: number;
  weakTopic: string;
}

export const STUDENT_PRACTICE_PROGRESS: PracticeProgress[] = [
  { courseCode: "BLM2512", completed: 12, averageScore: 7.4, weakTopic: "Ağaç dolaşımları" },
  { courseCode: "BLM3021", completed: 5, averageScore: 8.1, weakTopic: "Asimptotik notasyon" },
];
