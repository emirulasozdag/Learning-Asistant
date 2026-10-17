import type {
  AnswerFeedback,
  AskRequest,
  AskResponse,
  CourseSummary,
  LearningRecord,
  MistakeSummary,
  PracticeItem,
  PracticeRequest,
  ReviewDecision,
  Rubric,
  RubricIn,
  SourceDetail,
} from "./types";

// Vite proxy /api önekini backend'e yönlendirir (vite.config.ts).
const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  courses: () => request<CourseSummary[]>("/courses"),

  source: (sourceId: string) => request<SourceDetail>(`/sources/${encodeURIComponent(sourceId)}`),

  ask: (body: AskRequest) =>
    request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(body) }),

  generatePractice: (body: PracticeRequest) =>
    request<PracticeItem>("/practice", { method: "POST", body: JSON.stringify(body) }),

  submitAnswer: (itemId: number, answer: string) =>
    request<AnswerFeedback>(`/practice/${itemId}/answer`, {
      method: "POST",
      body: JSON.stringify({ answer }),
    }),

  learningRecord: (courseId: number) =>
    request<LearningRecord>(`/courses/${courseId}/learning-record`),

  frequentMistakes: (courseId: number) =>
    request<MistakeSummary[]>(`/instructor/courses/${courseId}/mistakes`),

  submitReview: (body: ReviewDecision) =>
    request<void>("/instructor/reviews", { method: "POST", body: JSON.stringify(body) }),

  rubrics: (courseId: number) => request<Rubric[]>(`/instructor/courses/${courseId}/rubrics`),

  createRubric: (courseId: number, body: RubricIn) =>
    request<Rubric>(`/instructor/courses/${courseId}/rubrics`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  uploadMaterial: (courseId: number, materialType: string, file: File) => {
    const form = new FormData();
    form.append("material_type", materialType);
    form.append("file", file);
    return request<{ document_id: number; chunk_count: number }>(
      `/courses/${courseId}/materials`,
      { method: "POST", body: form },
    );
  },
};
