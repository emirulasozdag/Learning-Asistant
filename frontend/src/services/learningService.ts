/** Öğrencinin kendi öğrenme kaydı — gerçek API (#20): yalnızca araştırma kaydı açıkken yapılan denemeler. */
import { api } from "../api/client";
import type { LearningRecord } from "../api/types";

export const learningService = {
  record(courseId: number, signal?: AbortSignal): Promise<LearningRecord> {
    return api.learningRecord(courseId, signal);
  },
};
