import { ChevronDown, SearchCheck } from "lucide-react";

import type { AskResponse } from "../../api/types";
import { cx } from "../../ui/cx";
import type { SelectSourceProps } from "./types";

/** "İncelenen bölümler": soru için bakılan parçalar, hangilerinin cevapta kullanıldığı. */
export default function RetrievalDetails({
  response,
  selectedSourceId,
  onSelectSource,
}: SelectSourceProps & { response: AskResponse }) {
  const hits = response.retrieval;
  const used = hits.filter((hit) => hit.used).length;

  return (
    <details className="group">
      <summary className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-control px-2 py-1 text-sm text-graphite transition-colors hover:bg-subtle hover:text-ink focus-visible:outline-2 focus-visible:outline-accent">
        <SearchCheck size={14} aria-hidden />
        İncelenen bölümler
        <span className="text-faint">
          {hits.length === 0 ? "eşleşen bölüm yok" : `${hits.length} bölüm, ${used} tanesi cevapta`}
        </span>
        <ChevronDown size={14} aria-hidden className="transition-transform group-open:rotate-180" />
      </summary>

      <div className="mt-2 rounded-panel border border-line bg-surface p-4">
        <p className="text-sm text-graphite">
          {hits.length === 0
            ? "Bu soru için ders materyalinde eşleşen bir bölüm bulunamadı."
            : used === 0
              ? `Soru için ${hits.length} bölüm incelendi; hiçbiri cevapta kullanılmadı. Bir bölüme tıklayıp kaynağı açabilirsin.`
              : `Soru için ${hits.length} bölüm incelendi, ${used} tanesi cevapta kullanıldı. Bir bölüme tıklayıp kaynağı açabilirsin.`}
        </p>

        {hits.length > 0 && (
          <ol className="mt-3 flex flex-col">
            {hits.map((hit, index) => {
              const active = hit.source_id === selectedSourceId;
              return (
                <li key={hit.source_id}>
                  <button
                    type="button"
                    onClick={() => onSelectSource(hit.source_id)}
                    aria-pressed={active}
                    className={cx(
                      "flex w-full items-baseline gap-3 border-b border-line py-2 text-left text-sm transition-colors last:border-b-0",
                      active ? "bg-accent-soft/50" : "hover:bg-canvas",
                    )}
                  >
                    <span className="w-5 shrink-0 text-faint tabular-nums">{index + 1}</span>
                    <span className="min-w-0 flex-1 truncate text-ink">{hit.document_title}</span>
                    {hit.page && <span className="shrink-0 text-graphite">sayfa {hit.page}</span>}
                    {hit.used && (
                      <span className="shrink-0 rounded-[3px] bg-marker-soft px-1 text-xs text-ink">
                        cevapta
                      </span>
                    )}
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
