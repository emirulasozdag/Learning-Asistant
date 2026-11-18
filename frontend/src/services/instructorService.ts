/**
 * Eğitmen görünümü — gerçek API: dersin soru-cevap etkinliği, sık hatalar (anonim, toplu),
 * pratik sorularının incelenmesi ve onay/düzeltme kararları (#20, #22).
 */
import { api } from "../api/client";
import type { CourseActivity, MistakeSummary, PracticeItemReview, ReviewDecision, ReviewOut } from "../api/types";

export const instructorService = {
  activity(courseId: number, signal?: AbortSignal): Promise<CourseActivity> {
    return api.courseActivity(courseId, signal);
  },

  mistakes(courseId: number, signal?: AbortSignal): Promise<MistakeSummary[]> {
    return api.frequentMistakes(courseId, signal);
  },

  practiceItems(courseId: number, signal?: AbortSignal): Promise<PracticeItemReview[]> {
    return api.practiceItems(courseId, signal);
  },

  review(decision: ReviewDecision): Promise<ReviewOut> {
    return api.submitReview(decision);
  },
};
