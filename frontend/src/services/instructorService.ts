/** Eğitmen görünümü — gerçek API: dersin soru-cevap etkinliği (kayıtlı mesajlardan, anonim). */
import { api } from "../api/client";
import type { CourseActivity } from "../api/types";

export const instructorService = {
  activity(courseId: number, signal?: AbortSignal): Promise<CourseActivity> {
    return api.courseActivity(courseId, signal);
  },
};
