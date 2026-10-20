/** AI Tutor — gerçek API: hibrit arama + cite-or-decline cevap, akışlı (SSE). */
import { api } from "../api/client";
import type { AskStreamEvent } from "../api/types";

export type QuickAction = "simpler" | "example" | "quiz";

/** Cevabın altındaki hızlı eylemler aynı sohbette takip sorusu olarak gönderilir. */
const QUICK_ACTION_PROMPTS: Record<QuickAction, string> = {
  simpler: "Bunu daha basit, adım adım anlatır mısın?",
  example: "Bunu ders materyalindeki bir örnekle gösterir misin?",
  quiz: "Bu konuyu anlayıp anlamadığımı görmek için bana ders materyaline dayanan kısa bir soru sorar mısın?",
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

  source(sourceId: string, signal?: AbortSignal) {
    return api.source(sourceId, signal);
  },
};
