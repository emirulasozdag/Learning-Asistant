import { ChevronDown } from "lucide-react";

import type { AskResponse, RetrievalHit } from "../../../api/types";
import { pageLabel } from "../../../labels";
import { formatTime } from "../../../text";
import { cx } from "../../../ui/cx";
import type { SelectSourceProps } from "../types";
import { formatScore } from "./format";

function hitLocation(hit: RetrievalHit): string {
  if (hit.page) return pageLabel(hit.page);
  if (hit.t_start != null) return formatTime(hit.t_start);
  return "";
}

/** Bir parçanın durumu: cevapta kullanıldı mı, anlamsal eşiğin altında mı kaldı. */
function hitStatus(
  hit: RetrievalHit,
  threshold: number | null,
): "used" | "moment" | "below" | "above" | "keyword" {
  if (hit.used) return "used";
  if (hit.video_moment) return "moment";
  if (hit.dense_score == null) return "keyword";
  if (threshold != null && hit.dense_score < threshold) return "below";
  return "above";
}

/** Öğrencinin gördüğü sade durum; puan ve eşik "Teknik ayrıntılar"da. */
const STATUS_LABEL = {
  used: "cevapta",
  moment: "durdurduğun an",
  below: "az ilgili",
  above: "ilgili",
  keyword: "kelimeyle bulundu",
} as const;

/**
 * "Nasıl bulundu?": sorunun ders materyalinde nasıl arandığı. Önce sade bir cümle ve incelenen
 * bölümler (çubuk, bölümün soruya ne kadar benzediğini gösterir); benzerlik puanları, alakasızlık
 * eşiği ve kelime sırası iç içe "Teknik ayrıntılar"da kapalı durur. Satıra dokununca o bölüm
 * kaynak panelinde açılır.
 */
export default function RetrievalMeter({
  response,
  selectedSourceId,
  onSelectSource,
  initiallyOpen = false,
}: SelectSourceProps & {
  response: AskResponse;
  /** Varsayılan kapalı: cevabın üstünü örtmesin. */
  initiallyOpen?: boolean;
}) {
  const hits = response.retrieval;
  const used = hits.filter((hit) => hit.used).length;
  const threshold = response.similarity_threshold;

  return (
    <details open={initiallyOpen} className="group rounded-panel border border-line bg-surface">
      <summary className="flex cursor-pointer list-none flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-3">
        <span className="text-base font-semibold text-ink">Nasıl bulundu?</span>
        <span className="text-sm text-graphite">
          İncelenen bölümler: {hits.length}, {used} tanesi cevapta
        </span>
        <ChevronDown
          size={16}
          aria-hidden
          className="ml-auto self-center text-graphite transition-transform group-open:rotate-180"
        />
      </summary>

      <div className="border-t border-line px-4 pt-3 pb-3">
        {hits.length === 0 ? (
          <p className="text-sm text-graphite">Bu soru için ders materyalinde eşleşen bir bölüm bulunamadı.</p>
        ) : (
          <>
            <p className="mb-2 max-w-[46rem] text-sm text-graphite">
              Sorun, ders materyalinde hem anlamca hem de kelime kelime arandı. Çubuk, bölümün soruna ne kadar
              benzediğini gösterir; cevapta kullanılanlar işaretlidir. Bir bölüme dokunup kaynağını açabilirsin.
            </p>
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
                        "grid w-full grid-cols-[minmax(0,1fr)_7.5rem] items-center gap-x-4 gap-y-1 rounded-control px-2 py-1.5 text-left text-sm transition-colors sm:grid-cols-[minmax(0,14rem)_minmax(0,1fr)_7.5rem]",
                        active ? "bg-accent-soft" : "hover:bg-subtle",
                      )}
                    >
                      <span className="truncate text-ink">
                        {hit.document_title}
                        <span className="text-graphite tabular-nums"> · {hitLocation(hit)}</span>
                      </span>
                      <span aria-hidden className="relative hidden h-2 rounded-full bg-meter-dim/60 sm:block">
                        {score != null && (
                          <span
                            className={cx(
                              "absolute inset-y-0 left-0 rounded-full",
                              status === "used" ? "bg-meter" : "bg-meter-dim",
                            )}
                            style={{ width: `${Math.max(0, Math.min(1, score)) * 100}%` }}
                          />
                        )}
                      </span>
                      <span className="text-right">
                        {status === "used" ? (
                          <span className="rounded-sm bg-marker-soft px-1.5 py-0.5 text-xs font-medium text-ink">
                            {STATUS_LABEL[status]}
                          </span>
                        ) : (
                          <span className="text-xs text-graphite">{STATUS_LABEL[status]}</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>

            <details className="group/tech mt-2">
              <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-control px-2 py-1 text-sm text-graphite hover:text-ink">
                Teknik ayrıntılar
                <ChevronDown size={14} aria-hidden className="transition-transform group-open/tech:rotate-180" />
              </summary>
              <div className="mt-1 flex flex-col gap-2 px-2 text-sm text-graphite">
                <p className="max-w-[46rem]">
                  Arama iki yolla yapılır: anlamsal benzerlik (0 ile 1 arası puan) ve anahtar kelime eşleşmesi.
                  {threshold != null &&
                    ` Benzerlik puanı ${formatScore(threshold)} eşiğinin altında kalan bölümler soruyla ilgisiz sayılır.`}
                </p>
                <ul className="flex flex-col gap-0.5">
                  {hits.map((hit) => (
                    <li key={hit.source_id} className="flex gap-3">
                      <span className="min-w-0 flex-1 truncate">
                        {hit.document_title} · {hitLocation(hit)}
                      </span>
                      <span className="shrink-0 tabular-nums">
                        {hit.dense_score != null
                          ? `benzerlik ${formatScore(hit.dense_score)}`
                          : hit.lexical_rank
                            ? `kelime araması sırası ${hit.lexical_rank}`
                            : "–"}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </details>
          </>
        )}
      </div>
    </details>
  );
}
