import { ChevronDown, SearchCheck } from "lucide-react";

import type { AskResponse } from "../../api/types";
import { cx } from "../../ui/cx";
import type { SelectSourceProps } from "./types";

// e5 benzerlikleri dar bir aralıkta toplanır (~0.70–0.90); çubuk bu aralığı genişletir.
const BAR_MIN = 0.6;
const BAR_MAX = 1.0;

/** "Nasıl bulundu": aramanın getirdiği parçalar, skorları ve hangilerinin kullanıldığı. */
export default function RetrievalDetails({
  response,
  selectedSourceId,
  onSelectSource,
}: SelectSourceProps & { response: AskResponse }) {
  const hits = response.retrieval;
  const threshold = response.similarity_threshold;
  const best = response.best_similarity;
  const used = hits.filter((hit) => hit.used).length;
  const gated = response.declined && threshold !== null && best !== null && best < threshold;

  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-control px-2 py-1 text-sm text-graphite transition-colors hover:bg-subtle hover:text-ink">
        <SearchCheck size={14} aria-hidden />
        Nasıl bulundu
        <span className="text-faint">
          {hits.length === 0
            ? "eşleşen parça yok"
            : `${hits.length} parça, ${used} alıntı`}
        </span>
        <ChevronDown size={14} aria-hidden className="transition-transform group-open:rotate-180" />
      </summary>

      <div className="mt-2 rounded-panel border border-line bg-surface p-4">
        <p className="text-sm text-graphite">
          Soru hem anlamına göre (multilingual-e5 vektörleri) hem kelimelerine göre (tam metin)
          arandı ve iki sıralama birleştirildi.
          {threshold !== null && best !== null && (
            <>
              {" "}
              En yüksek anlamsal benzerlik{" "}
              <strong className="font-medium text-ink tabular-nums">{best.toFixed(2)}</strong>,
              ilgisizlik eşiği <span className="tabular-nums">{threshold.toFixed(2)}</span>.
            </>
          )}
          {gated && " Benzerlik eşiğin altında kaldığı için soru modele hiç gönderilmedi."}
        </p>

        {hits.length > 0 && (
          <ol className="mt-3 flex flex-col">
            <li className="grid grid-cols-[1.25rem_minmax(0,1fr)_7rem_4.5rem] gap-3 border-b border-line pb-1.5 text-xs text-faint">
              <span>#</span>
              <span>Parça</span>
              <span>Anlamsal</span>
              <span className="text-right">Kelime</span>
            </li>
            {hits.map((hit, index) => {
              const active = hit.source_id === selectedSourceId;
              const width =
                hit.dense_score === null
                  ? 0
                  : Math.max(0, Math.min(1, (hit.dense_score - BAR_MIN) / (BAR_MAX - BAR_MIN)));
              return (
                <li key={hit.source_id}>
                  <button
                    type="button"
                    onClick={() => onSelectSource(hit.source_id)}
                    className={cx(
                      "grid w-full grid-cols-[1.25rem_minmax(0,1fr)_7rem_4.5rem] items-center gap-3 border-b border-line py-2 text-left text-sm last:border-b-0 transition-colors",
                      active ? "bg-accent-soft/50" : "hover:bg-canvas",
                    )}
                  >
                    <span className="text-faint tabular-nums">{index + 1}</span>
                    <span className="flex min-w-0 items-baseline gap-1">
                      <span className="truncate text-ink">{hit.document_title}</span>
                      {hit.page && <span className="shrink-0 text-graphite">s. {hit.page}</span>}
                      {hit.used && (
                        <span className="ml-1 shrink-0 rounded-[3px] bg-marker-soft px-1 text-[11px] text-ink">
                          alıntı
                        </span>
                      )}
                    </span>
                    <span className="flex items-center gap-2" title="Anlamsal benzerlik">
                      <span className="h-1 flex-1 overflow-hidden rounded-full bg-subtle">
                        <span className="block h-full rounded-full bg-accent" style={{ width: `${width * 100}%` }} />
                      </span>
                      <span className="w-8 text-right tabular-nums">
                        {hit.dense_score?.toFixed(2) ?? "—"}
                      </span>
                    </span>
                    <span className="text-right text-graphite tabular-nums">
                      {hit.lexical_rank ? `${hit.lexical_rank}.` : "—"}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </details>
  );
}
