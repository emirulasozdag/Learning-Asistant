import { useEffect, useState } from "react";

import type { DocumentOut } from "../../api/types";
import { materialTotals, type MaterialTotals } from "../../labels";
import { courseService, type Course } from "../../services/courseService";

/** Bir dersin bilgi tabanının özeti: tamamı gerçek materyal listesinden hesaplanır. */
export interface MaterialSummary {
  documents: number;
  totals: MaterialTotals;
  chunks: number;
  /** En son yüklenen dokümanın zamanı (ISO); doküman yoksa null. */
  lastUpload: string | null;
}

/** Ders başına özet; `undefined` = yükleniyor, `null` = alınamadı. */
export type MaterialSummaries = Record<number, MaterialSummary | null | undefined>;

export function summarize(documents: DocumentOut[]): MaterialSummary {
  return {
    documents: documents.length,
    totals: materialTotals(documents),
    chunks: documents.reduce((sum, d) => sum + d.chunk_count, 0),
    lastUpload: documents.reduce<string | null>(
      (latest, d) => (latest === null || d.created_at > latest ? d.created_at : latest),
      null,
    ),
  };
}

/** Derslerin materyal özetlerini paralel getirir; biri başarısız olursa diğerleri etkilenmez. */
export function useMaterialSummaries(courses: Course[]): MaterialSummaries {
  const [summaries, setSummaries] = useState<MaterialSummaries>({});
  const key = courses.map((course) => course.id).join(",");

  useEffect(() => {
    const controller = new AbortController();
    for (const id of key ? key.split(",").map(Number) : []) {
      courseService
        .materials(id, controller.signal)
        .then((documents) => {
          if (!controller.signal.aborted) setSummaries((map) => ({ ...map, [id]: summarize(documents) }));
        })
        .catch(() => {
          if (!controller.signal.aborted) setSummaries((map) => ({ ...map, [id]: null }));
        });
    }
    return () => controller.abort();
  }, [key]);

  return summaries;
}
