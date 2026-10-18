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

/** "Nasıl bulundu": aramanın getirdiği bir parça ve skorları. */
export interface RetrievalHit {
  source_id: string;
  document_title: string;
  page: number | null;
  /** Anlamsal benzerlik (0–1). */
  dense_score: number | null;
  /** Kelime aramasındaki sıra (1 = en iyi). */
  lexical_rank: number | null;
  used: boolean;
}

export interface AskResponse {
  /** [1], [2]... işaretleri `citations` sırasına karşılık gelir. */
  answer: string | null;
  /** "llm": model kaynaklardan yazdı; "extractive": LLM yok, en ilgili parça alıntılandı. */
  mode: "llm" | "extractive";
  citations: Citation[];
  declined: boolean;
  decline_reason: string | null;
  suggested_sources: Citation[];
  conversation_id: number | null;
  retrieval: RetrievalHit[];
  similarity_threshold: number | null;
  best_similarity: number | null;
  model: string | null;
}

/** /ask/stream olayları (Server-Sent Events). */
export type AskStreamEvent =
  | { type: "retrieval"; hits: RetrievalHit[] }
  | { type: "delta"; text: string }
  | { type: "done"; response: AskResponse }
  | { type: "error"; detail: string };

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
  role: "student" | "instructor" | "ta" | null;
}

export interface CourseCreate {
  code: string;
  name: string;
  language: "tr" | "en";
}

export type MaterialType = "textbook" | "notes" | "slides" | "past_exam" | "transcript" | "video";

export interface DocumentOut {
  id: number;
  course_id: number;
  title: string;
  material_type: MaterialType;
  filename: string;
  page_count: number;
  chunk_count: number;
  created_at: string;
  file_url: string;
  /** Yalnızca yükleme cevabında: hattın adım adım özeti. */
  report: IngestionReport | null;
}

export interface IngestionReport {
  pages_read: number;
  empty_pages: number;
  repeated_lines_removed: number;
  page_numbers_removed: number;
  chunks: number;
  vectors: number;
  vector_dim: number;
  embedding_model: string;
  timings_ms: Record<"parse" | "clean" | "chunk" | "embed", number>;
}

export interface ChunkPreview {
  id: number;
  ordinal: number;
  page: number | null;
  text: string;
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
  /** Yalnızca PDF: sayfa görüntüsü ve alıntılanan satırların yeri (sayfaya oranla 0–1). */
  page_image_url: string | null;
  highlights: Highlight[];
}

export interface Highlight {
  x: number;
  y: number;
  width: number;
  height: number;
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
