import { FileText } from "lucide-react";

import type { Citation } from "../../api/types";
import { cx } from "../../ui/cx";
import type { SelectSourceProps } from "./types";

/** Cevabın dayandığı kaynaklar: numaralı, tıklanınca sağda sayfa açılır. */
export default function SourceCards({
  citations,
  numbered = true,
  selectedSourceId,
  onSelectSource,
}: SelectSourceProps & { citations: Citation[]; numbered?: boolean }) {
  if (citations.length === 0) return null;
  return (
    <ul className="grid gap-2 sm:grid-cols-2">
      {citations.map((citation, index) => {
        const active = citation.source_id === selectedSourceId;
        const title = citation.document_title ?? "Kaynak";
        return (
          <li key={citation.source_id}>
            <button
              type="button"
              onClick={() => onSelectSource(citation.source_id)}
              aria-pressed={active}
              className={cx(
                "flex w-full items-center gap-3 rounded-panel border px-3 py-2 text-left transition-colors",
                active
                  ? "border-accent bg-accent-soft/60"
                  : "border-line bg-surface hover:border-line-strong hover:bg-canvas",
              )}
            >
              <span
                aria-hidden
                className={cx(
                  "flex size-7 shrink-0 items-center justify-center rounded ring-1",
                  active ? "bg-surface text-accent ring-accent-line" : "bg-canvas text-graphite ring-line",
                )}
              >
                <FileText size={14} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-base font-medium text-ink">{title}</span>
                <span className="block text-sm text-graphite">
                  {citation.page ? `Sayfa ${citation.page}` : "Doküman"}
                </span>
              </span>
              {numbered && (
                <span
                  className={cx(
                    "flex h-[18px] min-w-[18px] items-center justify-center rounded-[3px] px-1 text-[11px] font-semibold text-ink tabular-nums",
                    active ? "bg-marker" : "bg-marker-soft",
                  )}
                >
                  {index + 1}
                </span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
