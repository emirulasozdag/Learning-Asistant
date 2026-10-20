import { useEffect, useState } from "react";

import { ApiError } from "../../api/client";
import type { SourceDetail } from "../../api/types";
import { tutorService } from "../../services/tutorService";

export type SourceFailure = "missing" | "failed";

/**
 * Bir alıntının ayrıntısını yükler. "missing": kaynak yok (404), tekrar denemek işe yaramaz;
 * "failed": ulaşılamadı. Kaynak değişince eski içerik gösterilmez.
 */
export function useSourceDetail(sourceId: string | null) {
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [failure, setFailure] = useState<{ id: string; kind: SourceFailure } | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!sourceId) return;
    let cancelled = false;
    const controller = new AbortController();
    tutorService
      .source(sourceId, controller.signal)
      .then((detail) => {
        if (!cancelled) setSource(detail);
      })
      .catch((reason: unknown) => {
        if (cancelled) return;
        setFailure({
          id: sourceId,
          kind: reason instanceof ApiError && reason.status === 404 ? "missing" : "failed",
        });
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [sourceId, attempt]);

  function retry() {
    setFailure(null);
    setAttempt((count) => count + 1);
  }

  return {
    source: source?.source_id === sourceId ? source : null,
    failure: failure?.id === sourceId ? failure.kind : null,
    retry,
  };
}
