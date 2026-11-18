import type { TutorTurn } from "./types";

/**
 * Tutor sohbetini sekme oturumunda saklar (#106): ders içinde başka bir sayfaya gidip dönünce
 * sohbet kaybolmaz. Yalnızca bitmiş turlar saklanır; tarayıcı depolaması kapalıysa sessizce
 * atlanır (sohbet yine çalışır). Sekme kapanınca silinir.
 */
interface Stored {
  turns: TutorTurn[];
  conversationId: number | null;
}

function key(courseId: number, scope = "tutor"): string {
  return scope === "tutor" ? `la.tutor.${courseId}` : `la.tutor.${courseId}.${scope}`;
}

export function loadSession(courseId: number, scope = "tutor"): Stored {
  try {
    const raw = sessionStorage.getItem(key(courseId, scope));
    if (!raw) return { turns: [], conversationId: null };
    const parsed = JSON.parse(raw) as Stored;
    return { turns: Array.isArray(parsed.turns) ? parsed.turns : [], conversationId: parsed.conversationId ?? null };
  } catch {
    return { turns: [], conversationId: null };
  }
}

export function saveSession(
  courseId: number,
  turns: TutorTurn[],
  conversationId: number | null,
  scope = "tutor",
): void {
  try {
    const finished = turns.filter((turn) => turn.done || turn.failure || turn.stopped);
    if (finished.length === 0 && conversationId == null) sessionStorage.removeItem(key(courseId, scope));
    else sessionStorage.setItem(key(courseId, scope), JSON.stringify({ turns: finished, conversationId }));
  } catch {
    // Depolama dolu ya da kapalı: sohbet yalnızca bu sayfada kalır.
  }
}
