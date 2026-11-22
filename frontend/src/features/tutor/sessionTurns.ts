import { studyCacheKey } from "../../auth/studyCache";
import type { TutorTurn } from "./types";

/**
 * Tutor sohbetini sekme oturumunda saklar (#106): ders içinde başka bir sayfaya gidip dönünce
 * sohbet kaybolmaz. Yalnızca bitmiş turlar saklanır; tarayıcı depolaması kapalıysa sessizce
 * atlanır (sohbet yine çalışır). Sekme kapanınca silinir. Kayıt kullanıcıya bağlıdır (#134).
 */
interface Stored {
  turns: TutorTurn[];
  conversationId: number | null;
}

const EMPTY: Stored = { turns: [], conversationId: null };

function key(userId: number | null | undefined, courseId: number, scope = "tutor"): string | null {
  return studyCacheKey("la.tutor.", userId, scope === "tutor" ? `${courseId}` : `${courseId}.${scope}`);
}

export function loadSession(userId: number | null | undefined, courseId: number, scope = "tutor"): Stored {
  const storageKey = key(userId, courseId, scope);
  if (!storageKey) return EMPTY;
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return { turns: [], conversationId: null };
    const parsed = JSON.parse(raw) as Stored;
    return { turns: Array.isArray(parsed.turns) ? parsed.turns : [], conversationId: parsed.conversationId ?? null };
  } catch {
    return { turns: [], conversationId: null };
  }
}

export function saveSession(
  userId: number | null | undefined,
  courseId: number,
  turns: TutorTurn[],
  conversationId: number | null,
  scope = "tutor",
): void {
  const storageKey = key(userId, courseId, scope);
  if (!storageKey) return;
  try {
    const finished = turns.filter((turn) => turn.done || turn.failure || turn.stopped);
    if (finished.length === 0 && conversationId == null) sessionStorage.removeItem(storageKey);
    else sessionStorage.setItem(storageKey, JSON.stringify({ turns: finished, conversationId }));
  } catch {
    // Depolama dolu ya da kapalı: sohbet yalnızca bu sayfada kalır.
  }
}
