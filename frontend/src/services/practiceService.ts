/** Pratik soruları — gerçek API (#16, #17). Soru kontrollerden geçmezse 422 `no_valid_item`. */
import { api } from "../api/client";
import type { AnswerFeedback, AnswerSubmission, PracticeItem, PracticeRequest } from "../api/types";

export const practiceService = {
  generate(body: PracticeRequest, signal?: AbortSignal): Promise<PracticeItem> {
    return api.generatePractice(body, signal);
  },

  answer(itemId: number, body: AnswerSubmission): Promise<AnswerFeedback> {
    return api.submitAnswer(itemId, body);
  },
};
