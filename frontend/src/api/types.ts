// backend/app/schemas ile birebir aynı sözleşmeler.

export interface Citation {
  source_id: string;
  document_title?: string | null;
  page?: number | null;
  t_start?: number | null;
  t_end?: number | null;
}

export interface AskRequest {
  course_id: number;
  question: string;
  video_time_s?: number | null;
  conversation_id?: number | null;
}

export interface AskResponse {
  answer: string | null;
  citations: Citation[];
  declined: boolean;
  decline_reason: string | null;
  suggested_sources: Citation[];
  conversation_id: number | null;
}

export type PracticeType = "mcq" | "short_answer" | "code_tracing";

export interface PracticeRequest {
  course_id: number;
  type: PracticeType;
  topic?: string | null;
  source_id?: string | null;
}

export interface PracticeItem {
  id: number;
  type: PracticeType;
  prompt: string;
  options: string[] | null;
  source: Citation;
}

export interface AnswerFeedback {
  score: number;
  max_score: number;
  missing_concepts: string[];
  explanation: string;
  citations: Citation[];
  follow_up_item_id: number | null;
}

export interface LearningRecord {
  course_id: number;
  attempts: { item_id: number; concept: string | null; score: number; max_score: number }[];
}

export interface MistakeSummary {
  concept: string;
  error_type: string;
  count: number;
  fixing_source_ids: string[];
}

export interface ReviewDecision {
  target_type: "message" | "practice_item";
  target_id: number;
  decision: "approve" | "correct";
  correction?: string | null;
}

export interface CourseSummary {
  id: number;
  code: string;
  name: string;
  language: "tr" | "en";
  role: "student" | "instructor" | "ta";
}

export interface SourceDetail {
  source_id: string;
  document_id: number;
  document_title: string;
  material_type: string;
  text: string;
  page: number | null;
  t_start: number | null;
  t_end: number | null;
  media_url: string | null;
}

export interface RubricCriterion {
  description: string;
  points: number;
}

export interface RubricIn {
  concept: string;
  reference_answer: string;
  criteria: RubricCriterion[];
  practice_item_id?: number | null;
  source_ids?: string[];
}

export interface Rubric extends RubricIn {
  id: number;
  course_id: number;
  approved: boolean;
}
