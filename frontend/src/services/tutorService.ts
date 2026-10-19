/**
 * AI Tutor — GERÇEK API: hibrit arama + cite-or-decline cevap, akışlı (SSE).
 * Önerilen sorular şimdilik mock (ileride dersin materyalinden üretilebilir).
 */
import { api } from "../api/client";
import type { AskStreamEvent } from "../api/types";
import { GENERIC_QUESTIONS, SUGGESTED_QUESTIONS } from "../mock/tutor";

export type QuickAction = "simpler" | "example";

/** Cevabın altındaki hızlı eylemler aynı sohbette takip sorusu olarak gönderilir. */
const QUICK_ACTION_PROMPTS: Record<QuickAction, string> = {
  simpler: "Bunu daha basit, adım adım anlatır mısın?",
  example: "Bunu ders materyalindeki bir örnekle gösterir misin?",
};

export const tutorService = {
  ask(
    courseId: number,
    question: string,
    conversationId: number | null,
    onEvent: (event: AskStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    return api.askStream(
      { course_id: courseId, question, conversation_id: conversationId },
      onEvent,
      signal,
    );
  },

  quickActionPrompt(action: QuickAction): string {
    return QUICK_ACTION_PROMPTS[action];
  },

  suggestedQuestions(courseCode: string): string[] {
    return SUGGESTED_QUESTIONS[courseCode] ?? GENERIC_QUESTIONS;
  },

  source(sourceId: string, signal?: AbortSignal) {
    return api.source(sourceId, signal);
  },
};
