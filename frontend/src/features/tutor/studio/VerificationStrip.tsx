import { Link2, ShieldCheck } from "lucide-react";

import type { ClaimCheck } from "../../../api/types";
import { formatSeconds } from "./format";

/**
 * Cevabın doğrulama özeti: gerçekte ne kontrol edildiyse onu söyler (#105).
 *
 * - Her zaman: her cümle getirilen bir kaynak bölümüne bağlı; bağlanamayanlar backend'de çıkarıldı.
 *   Bu yalnızca bağlantıdır, anlamca karşılaştırma değildir; yeşil kalkan gösterilmez.
 * - İddia kontrolü yapıldıysa (`claim_check.status === "checked"`, #10): her iddia kaynakla
 *   ayrıca karşılaştırıldı; yalnızca o zaman "kaynakla karşılaştırıldı" denir.
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
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-xs text-graphite">
      {checked ? (
        <span
          title="Her iddia, alıntılanan kaynak bölümüyle ayrıca karşılaştırıldı; desteklenmeyenler çıkarıldı."
          className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success-soft px-2.5 py-1 font-medium text-success"
        >
          <ShieldCheck size={13} aria-hidden />
          {claims} iddia kaynakla karşılaştırıldı
        </span>
      ) : (
        <span
          title="Her cümle bir ders kaynağına bağlı; bağlanamayanlar çıkarıldı. Anlamın kaynakla aynı olduğu ayrıca denetlenmedi: önemli konularda kaynağı açıp karşılaştır."
          className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 font-medium text-ink-2"
        >
          <Link2 size={13} aria-hidden />
          {claims} cümle kaynağa bağlı
        </span>
      )}
      {!checked && <span>anlamı ayrıca denetlenmedi</span>}
      {removed > 0 && <span>{removed} dayanaksız cümle çıkarıldı</span>}
      {videos > 0 && <span>{videos} video</span>}
      {(documents > 0 || videos === 0) && <span>{documents} doküman</span>}
      {elapsedMs != null && <span>cevap {formatSeconds(elapsedMs)}</span>}
    </div>
  );
}
