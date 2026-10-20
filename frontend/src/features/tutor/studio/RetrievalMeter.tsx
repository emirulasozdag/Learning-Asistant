import { ChevronDown } from "lucide-react";

import type { AskResponse, RetrievalHit } from "../../../api/types";
import { formatTime } from "../../../text";
import { cx } from "../../../ui/cx";
import type { SelectSourceProps } from "../types";
import { formatScore } from "./format";

function hitLocation(hit: RetrievalHit): string {
  if (hit.page) return `s.${hit.page}`;
  if (hit.t_start != null) return formatTime(hit.t_start);
  return "";
}

/** Bir parçanın durumu: cevapta kullanıldı mı, anlamsal eşiğin altında mı kaldı. */
function hitStatus(hit: RetrievalHit, threshold: number | null): "used" | "below" | "above" | "keyword" {
  if (hit.used) return "used";
  if (hit.dense_score == null) return "keyword";
  if (threshold != null && hit.dense_score < threshold) return "below";
  return "above";
}

const STATUS_LABEL = {
  used: "kullanıldı",
  below: "eşik altı",
  above: "eşik üstü",
  keyword: "kelime eşleşmesi",
} as const;

/**
 * "Nasıl bulundu": hibrit aramanın getirdiği parçalar. Çubuk anlamsal benzerliği, dikey çizgi
 * alakasızlık eşiğini gösterir; kelime aramasıyla gelen parçada sıra yazılır. Satıra dokununca
 * o parça kaynak panelinde açılır.
 */
export default function RetrievalMeter({
  response,
  selectedSourceId,
  onSelectSource,
  initiallyOpen = true,
}: SelectSourceProps & {
  response: AskResponse;
  /** Dar ekranda kapalı başlar: cevabın üstünü örtmesin. */
  initiallyOpen?: boolean;
}) {
  const hits = response.retrieval;
  const used = hits.filter((hit) => hit.used).length;
  const threshold = response.similarity_threshold;

  return (
    <details open={initiallyOpen} className="group rounded-panel border border-line bg-surface shadow-card">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3">
        <span className="text-base font-semibold text-ink">Nasıl bulundu</span>
        <span className="text-sm text-graphite">
          İncelenen bölümler: {hits.length}, {used} tanesi cevapta
        </span>
        <span className="ml-auto flex items-center gap-2 font-mono text-xs text-graphite">
          anlamsal + anahtar kelime{threshold != null ? ` · eşik ${formatScore(threshold)}` : ""}
          <ChevronDown size={14} aria-hidden className="transition-transform group-open:rotate-180" />
        </span>
      </summary>

      <div className="border-t border-line px-4 pt-2 pb-3">
        <p className="sr-only">
          {hits.length === 0
            ? "Bu soru için ders materyalinde eşleşen bir bölüm bulunamadı."
            : `Soru için ${hits.length} bölüm incelendi, ${used} tanesi cevapta kullanıldı.`}
        </p>
        {hits.length === 0 ? (
          <p className="py-2 text-sm text-graphite">Bu soru için ders materyalinde eşleşen bir bölüm bulunamadı.</p>
        ) : (
          <ol className="flex max-h-[28vh] flex-col overflow-y-auto">
            {hits.map((hit) => {
              const status = hitStatus(hit, threshold);
              const active = hit.source_id === selectedSourceId;
              const score = hit.dense_score;
              return (
                <li key={hit.source_id}>
                  <button
                    type="button"
                    onClick={() => onSelectSource(hit.source_id)}
                    aria-pressed={active}
                    className={cx(
                      "grid w-full grid-cols-[minmax(0,13rem)_minmax(0,1fr)_9.5rem] items-center gap-4 rounded-control px-2 py-1.5 text-left text-sm transition-colors",
                      active ? "bg-accent-soft" : "hover:bg-subtle",
                    )}
                  >
                    <span className="truncate text-ink">
                      {hit.document_title}
                      <span className="text-graphite"> · {hitLocation(hit)}</span>
                    </span>
                    <span aria-hidden className="relative h-2 rounded-full bg-meter-dim/60">
                      {score != null && (
                        <span
                          className={cx(
                            "absolute inset-y-0 left-0 rounded-full",
                            status === "used" ? "bg-meter" : "bg-meter-dim",
                          )}
                          style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
                        />
                      )}
                      {threshold != null && (
                        <span
                          className="absolute -inset-y-1.5 w-px bg-ink/70"
                          style={{ left: `${threshold * 100}%` }}
                        />
                      )}
                    </span>
                    <span
                      className={cx(
                        "text-right font-mono text-xs tabular-nums",
                        status === "used" ? "text-ink" : "text-graphite",
                      )}
                    >
                      {score != null ? formatScore(score) : hit.lexical_rank ? `#${hit.lexical_rank}` : "–"}
                      {" · "}
                      {STATUS_LABEL[status]}
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
