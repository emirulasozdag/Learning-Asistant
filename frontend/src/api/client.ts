import type {
  AnswerFeedback,
  AnswerSubmission,
  AskRequest,
  AskResponse,
  AskStreamEvent,
  ChunkPreview,
  CourseActivity,
  CourseCreate,
  CourseOutline,
  CourseSummary,
  CourseUpdate,
  Consent,
  DemoInfo,
  ConsentUpdate,
  DocumentOut,
  JoinCode,
  LearningRecord,
  LoginRequest,
  MaterialType,
  Me,
  MistakeSummary,
  PracticeItem,
  PracticeRequest,
  RegisterRequest,
  ReviewDecision,
  Rubric,
  RubricIn,
  SourceDetail,
  TutorStreamEvent,
  TutorTurnRequest,
} from "./types";

// Vite proxy /api önekini backend'e yönlendirir (vite.config.ts).
const BASE = "/api";

/**
 * API hatası. `message` eskisi gibi okunur (backend'in `detail` metni ya da tarayıcının
 * hata metni); `kind` hatanın nereden geldiğini ayırt eder:
 * - "network": istek sunucuya ulaşmadı,
 * - "http": sunucu hata koduyla cevap verdi (`status`),
 * - "stream": cevap akışı bozuldu ya da yarıda kesildi.
 */
export class ApiError extends Error {
  readonly kind: "network" | "http" | "stream";
  readonly status?: number;
  /** Backend'in hata kodu (`not_authenticated`, `consent_required`…); yoksa boş. */
  readonly code?: string;

  constructor(message: string, kind: "network" | "http" | "stream", status?: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

let onUnauthorized: (() => void) | null = null;

/** Oturum düşünce (401) çağrılır; AuthProvider kullanıcıyı çıkış yapmış sayar. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

/** `fetch` ile aynı; ağ hatasını `ApiError("network")` yapar. İptal (abort) olduğu gibi geçer. */
async function send(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init);
  } catch (reason) {
    if (init?.signal?.aborted) throw reason;
    throw new ApiError(reason instanceof Error ? reason.message : String(reason), "network");
  }
}

async function httpError(response: Response): Promise<ApiError> {
  const { detail, code } = await errorBody(response);
  // Hatalı şifre de 401 döner; o durumda oturum zaten yoktur, çıkış kancası çağrılmaz.
  if (response.status === 401 && !response.url.endsWith("/auth/login")) onUnauthorized?.();
  return new ApiError(detail, "http", response.status, code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

/** Backend'in `detail` mesajı (Türkçe; yoksa HTTP durumu) ve varsa hata kodu. */
async function errorBody(response: Response): Promise<{ detail: string; code?: string }> {
  try {
    const body = (await response.json()) as { detail?: unknown; code?: unknown };
    const code = typeof body.code === "string" ? body.code : undefined;
    if (typeof body.detail === "string") return { detail: body.detail, code };
    // FastAPI doğrulama hatası: alan hataları listesi
    if (Array.isArray(body.detail)) return { detail: "Girilen bilgiler geçersiz.", code };
  } catch {
    // JSON olmayan hata gövdesi
  }
  return { detail: `İstek başarısız (${response.status})` };
}

/**
 * /ask/stream: Server-Sent Events akışını okur, her olayı `onEvent` ile bildirir.
 * `signal` ile iptal edilebilir.
 */
function askStream(
  body: AskRequest,
  onEvent: (event: AskStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return readSse("/ask/stream", body, parseAskEvent, onEvent, signal);
}

/** /tutor/turn/stream: AI Tutor turu (CONTRACTS.md §9). */
function tutorStream(
  body: TutorTurnRequest,
  onEvent: (event: TutorStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  return readSse("/tutor/turn/stream", body, parseTutorEvent, onEvent, signal);
}

// SSE verisi olay adına göre backend sözleşmesindeki şekli alır (types.ts).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type SsePayload = any;

async function readSse<E>(
  path: string,
  body: unknown,
  parse: (name: string, payload: SsePayload) => E | null,
  onEvent: (event: E) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await send(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    throw await httpError(response);
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;
      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseSseBlock(block);
        const event = parsed && parse(parsed.name, parsed.payload);
        if (event) onEvent(event);
        boundary = buffer.indexOf("\n\n");
      }
    }
  } catch (reason) {
    if (signal?.aborted || reason instanceof ApiError) throw reason;
    // Akış yarıda koptu (bağlantı düştü, sunucu kapandı).
    throw new ApiError(reason instanceof Error ? reason.message : String(reason), "stream");
  }
}

function parseSseBlock(block: string): { name: string; payload: SsePayload } | null {
  let name = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!name || !data) return null;
  try {
    return { name, payload: JSON.parse(data) };
  } catch {
    throw new ApiError("Cevap akışı okunamadı", "stream");
  }
}

function parseAskEvent(name: string, payload: SsePayload): AskStreamEvent | null {
  switch (name) {
    case "retrieval":
      return { type: "retrieval", hits: payload };
    case "delta":
      return { type: "delta", text: payload.text };
    case "done":
      return { type: "done", response: payload };
    case "error":
      return { type: "error", detail: payload.detail };
    default:
      return null;
  }
}

function parseTutorEvent(name: string, payload: SsePayload): TutorStreamEvent | null {
  switch (name) {
    case "status":
      return { type: "status", tool: payload.tool, label: payload.label };
    case "retrieval":
      return { type: "retrieval", blockIndex: payload.block_index, hits: payload.hits };
    case "delta":
      return { type: "delta", blockIndex: payload.block_index, text: payload.text };
    case "block":
      return { type: "block", index: payload.index, block: payload.block };
    case "done":
      return { type: "done", response: payload };
    case "error":
      return { type: "error", detail: payload.detail };
    default:
      return null;
  }
}

export const api = {
  me: (signal?: AbortSignal) => request<Me>("/me", { signal }),

  login: (body: LoginRequest) =>
    request<Me>("/auth/login", { method: "POST", body: JSON.stringify(body) }),

  register: (body: RegisterRequest) =>
    request<Me>("/auth/register", { method: "POST", body: JSON.stringify(body) }),

  logout: () => request<void>("/auth/logout", { method: "POST" }),

  /** Sunum modu kapalıysa 404 döner. */
  demoInfo: (signal?: AbortSignal) => request<DemoInfo>("/auth/demo", { signal }),

  demoLogin: (role: "instructor" | "student") =>
    request<Me>("/auth/demo-login", { method: "POST", body: JSON.stringify({ role }) }),

  updateConsent: (body: ConsentUpdate) =>
    request<Consent>("/me/consent", { method: "PUT", body: JSON.stringify(body) }),

  courses: () => request<CourseSummary[]>("/courses"),

  joinCourse: (code: string) =>
    request<CourseSummary>("/courses/join", { method: "POST", body: JSON.stringify({ code }) }),

  joinCode: (courseId: number, signal?: AbortSignal) =>
    request<JoinCode>(`/courses/${courseId}/join-code`, { signal }),

  rotateJoinCode: (courseId: number) =>
    request<JoinCode>(`/courses/${courseId}/join-code`, { method: "POST" }),

  createCourse: (body: CourseCreate) =>
    request<CourseSummary>("/courses", { method: "POST", body: JSON.stringify(body) }),

  updateCourse: (courseId: number, body: CourseUpdate) =>
    request<CourseSummary>(`/courses/${courseId}`, { method: "PATCH", body: JSON.stringify(body) }),

  courseOutline: (courseId: number, signal?: AbortSignal) =>
    request<CourseOutline>(`/courses/${courseId}/outline`, { signal }),

  askStream,

  tutorStream,

  source: (sourceId: string, signal?: AbortSignal) =>
    request<SourceDetail>(`/sources/${encodeURIComponent(sourceId)}`, { signal }),

  ask: (body: AskRequest) =>
    request<AskResponse>("/ask", { method: "POST", body: JSON.stringify(body) }),

  generatePractice: (body: PracticeRequest) =>
    request<PracticeItem>("/practice", { method: "POST", body: JSON.stringify(body) }),

  submitAnswer: (itemId: number, body: AnswerSubmission) =>
    request<AnswerFeedback>(`/practice/${itemId}/answer`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  learningRecord: (courseId: number) =>
    request<LearningRecord>(`/courses/${courseId}/learning-record`),

  courseActivity: (courseId: number, signal?: AbortSignal) =>
    request<CourseActivity>(`/instructor/courses/${courseId}/activity`, { signal }),

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

  materials: (courseId: number, signal?: AbortSignal) =>
    request<DocumentOut[]>(`/courses/${courseId}/materials`, { signal }),

  documentChunks: (documentId: number) =>
    request<ChunkPreview[]>(`/documents/${documentId}/chunks`),

  deleteDocument: async (documentId: number) => {
    const response = await send(`${BASE}/documents/${documentId}`, { method: "DELETE" });
    if (!response.ok) throw await httpError(response);
  },

  uploadMaterial: (courseId: number, materialType: MaterialType, file: File, title?: string) => {
    const form = new FormData();
    form.append("material_type", materialType);
    form.append("file", file);
    // ADR-3: eğitmen dosyanın bu ders için onaylı materyal olduğunu beyan eder (formda işaretlenir).
    form.append("declaration", "true");
    if (title) form.append("title", title);
    return request<DocumentOut>(`/courses/${courseId}/materials`, { method: "POST", body: form });
  },
};
