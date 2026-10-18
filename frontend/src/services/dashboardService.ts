/**
 * Dashboard özetleri — ŞU AN MOCK (ekip görevi: docs/UI_GOREVLERI.md).
 * Gerçek kaynak: messages tablosu (sorular) ve öğrenme kaydı (FR-15).
 */
import {
  INSTRUCTOR_SUMMARY,
  STUDENT_PRACTICE_PROGRESS,
  STUDENT_RECENT_QUESTIONS,
  type InstructorSummary,
  type PracticeProgress,
  type RecentQuestion,
} from "../mock/dashboard";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const dashboardService = {
  async instructorSummary(): Promise<InstructorSummary> {
    await delay(150);
    return INSTRUCTOR_SUMMARY;
  },

  async recentQuestions(): Promise<RecentQuestion[]> {
    await delay(150);
    return STUDENT_RECENT_QUESTIONS;
  },

  async practiceProgress(): Promise<PracticeProgress[]> {
    await delay(150);
    return STUDENT_PRACTICE_PROGRESS;
  },
};

export type { InstructorSummary, PracticeProgress, RecentQuestion };
