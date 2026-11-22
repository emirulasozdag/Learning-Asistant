import { ChevronDown, Link2, ShieldCheck } from "lucide-react";

import type { ClaimCheck } from "../../../api/types";
import { formatSeconds } from "./format";

/**
 * Cevabın doğrulama özeti: gerçekte ne kontrol edildiyse onu, sade cümleyle söyler (#105).
 *
 * - Her zaman: her cümle getirilen bir kaynak bölümüne bağlı; bağlanamayanlar backend'de çıkarıldı.
 *   Bu yalnızca bağlantıdır, anlamca karşılaştırma değildir; yeşil kalkan gösterilmez.
 * - İddia kontrolü yapıldıysa (`claim_check.status === "checked"`, #10): her iddia kaynakla
 *   ayrıca karşılaştırıldı; yalnızca o zaman "kaynakla karşılaştırıldı" denir.
 *
 * Ayrıntı (ne demek, ne kadar sürdü) "Nasıl denetlendi?" açılır bölümündedir; üstteki satır
 * öğrencinin bilmesi gerekeni söyler.
 */
export default function VerificationStrip({
  claims,
  removed,
  check,
  videos = 0,
  documents,
  elapsedMs,
}: {
  claims: number;
  removed: number;
  check?: ClaimCheck | null;
  /** Alıntılanan ders videosu sayısı (transkript). */
  videos?: number;
  /** Alıntılanan doküman (PDF, slayt…) sayısı. */
  documents: number;
  elapsedMs: number | null;
}) {
  const checked = check?.status === "checked";
  return (
    <div className="flex flex-col gap-1.5 text-sm text-graphite">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {checked ? (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success-soft px-2.5 py-1 font-medium text-success">
            <ShieldCheck size={14} aria-hidden />
            {claims} iddia kaynakla karşılaştırıldı
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-2.5 py-1 font-medium text-ink-2">
            <Link2 size={14} aria-hidden />
            {claims} cümle kaynağa bağlı
          </span>
        )}
        {!checked && <span>anlamı ayrıca denetlenmedi</span>}
        {removed > 0 && <span>{removed} dayanaksız cümle çıkarıldı</span>}
        <span className="inline-flex flex-wrap items-center gap-x-1.5">
          <span>Dayandığı yer:</span>
          {videos > 0 && <span>{videos} video</span>}
          {videos > 0 && documents > 0 && <span aria-hidden>·</span>}
          {(documents > 0 || videos === 0) && <span>{documents} doküman</span>}
        </span>
      </div>

      <details className="group self-start">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-control text-sm text-graphite hover:text-ink">
          Nasıl denetlendi?
          <ChevronDown size={14} aria-hidden className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="mt-1.5 flex max-w-[46rem] flex-col gap-1.5 text-sm text-graphite">
          {checked ? (
            <p>
              Her iddia, alıntılanan kaynak bölümüyle ayrıca karşılaştırıldı; kaynakla desteklenmeyenler cevaptan
              çıkarıldı.
            </p>
          ) : (
            <p>
              Cevabın her cümlesi ders materyalinden bir bölüme bağlı; bağlanamayan cümleler çıkarıldı. Cümlenin
              anlamının kaynakla aynı olduğu ayrıca denetlenmedi: önemli konularda dipnota dokunup kaynağı
              karşılaştır.
            </p>
          )}
          {elapsedMs != null && <p className="tabular-nums">Cevap süresi: {formatSeconds(elapsedMs)}.</p>}
        </div>
      </details>
    </div>
  );
}
