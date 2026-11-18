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

function key(courseId: number): string {
  return `la.tutor.${courseId}`;
}

export function loadSession(courseId: number): Stored {
  try {
    const raw = sessionStorage.getItem(key(courseId));
    if (!raw) return { turns: [], conversationId: null };
    const parsed = JSON.parse(raw) as Stored;
    return { turns: Array.isArray(parsed.turns) ? parsed.turns : [], conversationId: parsed.conversationId ?? null };
  } catch {
    return { turns: [], conversationId: null };
  }
}

export function saveSession(courseId: number, turns: TutorTurn[], conversationId: number | null): void {
  try {
    const finished = turns.filter((turn) => turn.done || turn.failure || turn.stopped);
    if (finished.length === 0 && conversationId == null) sessionStorage.removeItem(key(courseId));
    else sessionStorage.setItem(key(courseId), JSON.stringify({ turns: finished, conversationId }));
  } catch {
    // Depolama dolu ya da kapalı: sohbet yalnızca bu sayfada kalır.
  }
}
