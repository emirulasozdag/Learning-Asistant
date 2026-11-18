import { useEffect, useState } from "react";

import type { FrameRef } from "../../api/types";
import { courseService } from "../../services/courseService";

/** Slayt değişimine bu kadar saniye yakın an "değişim anı" sayılır; iki kare birlikte gösterilir. */
export const SLIDE_CHANGE_WINDOW_S = 2;

/** `seconds` anında ekranda olan kare (t_start ≤ s < t_end); yoksa null. */
export function frameAt(frames: FrameRef[], seconds: number): FrameRef | null {
  return frames.find((frame) => frame.t_start <= seconds && seconds < frame.t_end) ?? null;
}

/**
 * An bir slayt değişimine `SLIDE_CHANGE_WINDOW_S` saniyeden yakınsa değişimden önceki ve sonraki
 * kare; değilse null. Kareler zamana göre sıralıdır (backend `ordinal` sırası).
 */
export function slideChangeNear(frames: FrameRef[], seconds: number): [FrameRef, FrameRef] | null {
  for (let index = 1; index < frames.length; index++) {
    const before = frames[index - 1];
    const after = frames[index];
    if (Math.abs(seconds - after.t_start) <= SLIDE_CHANGE_WINDOW_S) return [before, after];
  }
  return null;
}

/** Görüntü tekrar denenirken tarayıcının önbelleğindeki hatayı kullanmaması için adres değişir. */
export function retryUrl(url: string, attempt: number): string {
  if (attempt === 0) return url;
  return `${url}${url.includes("?") ? "&" : "?"}deneme=${attempt}`;
}

/**
 * Videonun kareleri, video başına bir kez yüklenir. Yüklenene kadar null; kare yoksa ya da
 * yüklenemezse boş liste (kareler yardımcıdır, cevap transkripte dayanır; hata gösterilmez).
 */
export function useFrames(documentId: number | null): FrameRef[] | null {
  const [state, setState] = useState<{ id: number | null; frames: FrameRef[] | null }>({ id: null, frames: null });
  useEffect(() => {
    if (documentId == null) return;
    const controller = new AbortController();
    courseService
      .frames(documentId, controller.signal)
      .then((frames) => {
        if (!controller.signal.aborted) setState({ id: documentId, frames });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ id: documentId, frames: [] });
      });
    return () => controller.abort();
  }, [documentId]);
  return documentId != null && state.id === documentId ? state.frames : null;
}
