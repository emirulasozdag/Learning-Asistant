import { FileText, PlayCircle } from "lucide-react";

import type { Citation } from "../../api/types";
import { pageLabel } from "../../labels";
import { formatTime } from "../../text";
import Card from "../../ui/Card";
import { cx } from "../../ui/cx";
import { FootnoteMark } from "./CitedText";
import type { SelectSourceProps } from "./types";

/**
 * Cevabın dayandığı kaynaklar: dipnot listesi gibi numaralı (cevaptaki fosforlu işaretlerle aynı
 * numara); tıklanınca kaynak açılır.
 */
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
        const isVideo = citation.page == null && citation.t_start != null;
        const Icon = isVideo ? PlayCircle : FileText;
        return (
          <Card
            as="li"
            key={citation.source_id}
            padding="none"
            interactive
            className={cx(active && "border-accent bg-accent-soft/60")}
          >
            <button
              type="button"
              onClick={() => onSelectSource(citation.source_id)}
              aria-pressed={active}
              className="flex w-full items-center gap-3 rounded-panel px-3 py-2.5 text-left"
            >
              {numbered ? (
                <FootnoteMark number={index + 1} className="shrink-0" />
              ) : (
                <Icon size={16} aria-hidden className={cx("shrink-0", active ? "text-accent" : "text-graphite")} />
              )}
              <span className="min-w-0 flex-1">
                <span className="block truncate text-base font-medium text-ink">{title}</span>
                <span className="block text-sm text-graphite tabular-nums">
                  {citation.page
                    ? pageLabel(citation.page)
                    : citation.t_start != null
                      ? formatTime(citation.t_start)
                      : "Doküman"}
                </span>
              </span>
            </button>
          </Card>
        );
      })}
    </ul>
  );
}
