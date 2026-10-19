import type {
  AnswerFeedback,
  AskRequest,
  AskResponse,
  AskStreamEvent,
  ChunkPreview,
  CourseCreate,
  CourseSummary,
  DocumentOut,
  LearningRecord,
  MaterialType,
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

  constructor(message: string, kind: "network" | "http" | "stream", status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
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
  return new ApiError(await errorMessage(response), "http", response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await send(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw await httpError(response);
  }
  return response.json() as Promise<T>;
}

/** Backend'in `detail` mesajını (Türkçe) gösterir; yoksa HTTP durumunu. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // JSON olmayan hata gövdesi
  }
  return `İstek başarısız (${response.status})`;
}

/**
 * /ask/stream: Server-Sent Events akışını okur, her olayı `onEvent` ile bildirir.
 * `signal` ile iptal edilebilir.
 */
async function askStream(
  body: AskRequest,
  onEvent: (event: AskStreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await send(`${BASE}/ask/stream`, {
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
        const event = parseSseBlock(block);
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

function parseSseBlock(block: string): AskStreamEvent | null {
  let name = "";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) name = line.slice(7);
    else if (line.startsWith("data: ")) data += line.slice(6);
  }
  if (!name || !data) return null;
  let payload;
  try {
    payload = JSON.parse(data);
  } catch {
    throw new ApiError("Cevap akışı okunamadı", "stream");
  }
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

export const api = {
  courses: () => request<CourseSummary[]>("/courses"),

  createCourse: (body: CourseCreate) =>
    request<CourseSummary>("/courses", { method: "POST", body: JSON.stringify(body) }),

  askStream,

  source: (sourceId: string, signal?: AbortSignal) =>
    request<SourceDetail>(`/sources/${encodeURIComponent(sourceId)}`, { signal }),

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
    if (title) form.append("title", title);
    return request<DocumentOut>(`/courses/${courseId}/materials`, { method: "POST", body: form });
  },
};
