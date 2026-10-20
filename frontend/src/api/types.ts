// backend/app/schemas ile birebir aynı sözleşmeler.

/** Kullanıcının bir dersteki rolü (ders başına). */
export type Role = "student" | "instructor" | "ta";

/** Uygulama hatalarının sabit kodu (docs/CONTRACTS.md §5). */
export type ErrorCode =
  | "course_not_found"
  | "source_not_found"
  | "conversation_not_found"
  | "document_not_found"
  | "unsupported_file_type"
  | "file_too_large"
  | "ingestion_failed"
  | "course_exists"
  | "no_valid_item"
  | "invalid_video"
  | "not_authenticated"
  | "insufficient_role"
  | "not_implemented"
  | "validation_error";

/** Hata zarfı: `detail` kullanıcıya gösterilebilir metin, `code` programın kullandığı sabit. */
export interface ApiErrorBody {
  detail: string;
  code: ErrorCode;
}

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

/**
 * Cevabın nasıl sonuçlandığı:
 * - answered: doğrulanmış, alıntılı cevap
 * - insufficient_evidence: materyalde yok
 * - unsupported: model yazdı ama alıntı doğrulamasından geçemedi
 * - model_refusal: model yanıtlamayı reddetti
 * - provider_failure: modele ulaşılamadı; en ilgili parça alıntılandı
 */
export type AskOutcome =
  | "answered"
  | "insufficient_evidence"
  | "unsupported"
  | "model_refusal"
  | "provider_failure";

export interface AskResponse {
  /** [1], [2]... işaretleri `citations` sırasına karşılık gelir. */
  answer: string | null;
  /** "llm": model kaynaklardan yazdı; "extractive": LLM yok, en ilgili parça alıntılandı. */
  mode: "llm" | "extractive";
  outcome: AskOutcome;
  /** Kaynağa dayanmadığı için cevaptan çıkarılan cümle sayısı. */
  unsupported_removed: number;
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

/**
 * /ask/stream olayları (Server-Sent Events). `delta` metni doğrulanmamış taslaktır;
 * `done` içindeki cevap doğrulanmıştır ve taslağın yerini her zaman alır.
 */
export type AskStreamEvent =
  | { type: "retrieval"; hits: RetrievalHit[] }
  | { type: "delta"; text: string }
  | { type: "done"; response: AskResponse }
  | { type: "error"; detail: string };

export type PracticeType = "mcq" | "short_answer" | "code_tracing";

export type Difficulty = "easy" | "medium" | "hard";

export interface PracticeRequest {
  course_id: number;
  type: PracticeType;
  topic?: string | null;
  source_id?: string | null;
  difficulty?: Difficulty | null;
  /** "Bu eksik üzerine çalış": bu denemenin eksiklerine yönelik yeni soru. */
  follow_up_of_attempt_id?: number | null;
}

/** Cevap anahtarı, referans cevap ve açıklama gönderimden önce hiçbir yanıtta dönmez. */
export interface PracticeItem {
  id: number;
  course_id: number;
  type: PracticeType;
  topic: string | null;
  difficulty: Difficulty;
  prompt: string;
  /** Yalnızca mcq. */
  options: string[] | null;
  source: Citation;
}

/** Tam biri dolu olur: short_answer/code_tracing → `answer_text`, mcq → `selected_option`. */
export interface AnswerSubmission {
  answer_text?: string | null;
  /** `PracticeItem.options` içindeki sıra (0'dan başlar). */
  selected_option?: number | null;
}

export interface AnswerFeedback {
  attempt_id: number;
  item_id: number;
  score: number;
  max_score: number;
  understood: string[];
  missing_concepts: string[];
  explanation: string;
  citations: Citation[];
  follow_up_item_id: number | null;
}

export interface LearningRecord {
  course_id: number;
  attempts: { item_id: number; concept: string | null; score: number; max_score: number }[];
}

/** Dersin soru-cevap etkinliği (eğitmen): kayıtlı mesajlardan hesaplanır, anonim. */
export interface CourseActivity {
  questions: number;
  conversations: number;
  answered: number;
  /** Materyalde yeterli dayanak yok. */
  not_covered: number;
  /** Doğrulanamadı ya da model reddetti. */
  not_generated: number;
  /** Modele ulaşılamadı. */
  unavailable: number;
  daily: { day: string; questions: number }[];
  top_sources: { source_id: string; document_title: string; page: number | null; citations: number }[];
  recent_questions: QuestionItem[];
  unanswered_questions: QuestionItem[];
}

export interface QuestionItem {
  question: string;
  outcome: AskOutcome;
  asked_at: string;
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

export type CourseLevel = "undergraduate" | "graduate";

/** Dersin tanıtım bilgileri: eğitmen girer, hepsi boş olabilir. */
export interface CourseInfo {
  instructor_name: string | null;
  term: string | null;
  level: CourseLevel | null;
  department: string | null;
  description: string | null;
}

export interface CourseSummary extends CourseInfo {
  id: number;
  code: string;
  name: string;
  language: "tr" | "en";
  role: Role | null;
}

export interface UserOut {
  id: number;
  name: string;
  email: string;
  title: string | null;
}

/** Kullanıcının bir dersteki rolü. */
export interface Membership {
  course_id: number;
  role: Role;
}

/** Araştırma/analiz kaydı için ayrı opt-in (varsayılan kapalı). */
export interface Consent {
  research_logging: boolean;
  consented_at: string | null;
  policy_version: string;
}

export interface ConsentUpdate {
  research_logging: boolean;
  policy_version: string;
}

/** `GET /me`: oturumdaki kullanıcı, ders üyelikleri ve onay durumu. */
export interface Me {
  user: UserOut;
  memberships: Membership[];
  consent: Consent;
}

/** Katılım kodu ile derse katılma. */
export interface JoinCourseRequest {
  code: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/** Rol alanı yoktur: eğitmen/TA rolü kayıtla alınamaz. */
export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
}

export interface CourseCreate extends Partial<CourseInfo> {
  code: string;
  name: string;
  language: "tr" | "en";
}

/** Kısmi güncelleme: yalnızca gönderilen alanlar değişir; boş metin alanı temizler. */
export type CourseUpdate = Partial<CourseInfo> & { name?: string; language?: "tr" | "en" };

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
  material_type: MaterialType;
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
