/**
 * Pratik — ŞU AN MOCK (ekip görevi: docs/UI_GOREVLERI.md).
 * Gerçek API: POST /practice (soru üret), POST /practice/{id}/answer (değerlendir).
 */
import {
  SAMPLE_FEEDBACK,
  SAMPLE_QUESTION,
  type PracticeFeedback,
  type PracticeQuestion,
} from "../mock/practice";

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export const practiceService = {
  async nextQuestion(_courseId: number, topic?: string): Promise<PracticeQuestion> {
    await delay(300);
    return topic ? { ...SAMPLE_QUESTION, topic } : SAMPLE_QUESTION;
  },

  async submit(_questionId: string, _answer: string): Promise<PracticeFeedback> {
    await delay(900);
    return SAMPLE_FEEDBACK;
  },
};

export type { PracticeFeedback, PracticeQuestion };
