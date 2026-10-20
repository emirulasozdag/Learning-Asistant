/**
 * AI Tutor — gerçek API. `turn`: orkestratörlü tur (/tutor/turn/stream, CONTRACTS.md §9);
 * `ask`: yalnızca kaynaklı cevap hattı (/ask/stream).
 */
import { api } from "../api/client";
import type { AskStreamEvent, TutorStreamEvent } from "../api/types";

export type QuickAction = "simpler" | "example" | "quiz";

/** Cevabın altındaki hızlı eylemler aynı sohbette takip sorusu olarak gönderilir. */
const QUICK_ACTION_PROMPTS: Record<QuickAction, string> = {
  simpler: "Bunu daha basit, adım adım anlatır mısın?",
  example: "Bunu ders materyalindeki bir örnekle gösterir misin?",
  quiz: "Bu konuda beni test et: bana bir soru sor.",
};

export const tutorService = {
  turn(
    courseId: number,
    message: string,
    conversationId: number | null,
    onEvent: (event: TutorStreamEvent) => void,
    signal?: AbortSignal,
  ): Promise<void> {
    return api.tutorStream(
      { course_id: courseId, message, conversation_id: conversationId },
      onEvent,
      signal,
    );
  },

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
