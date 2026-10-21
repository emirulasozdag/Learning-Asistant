import { ShieldCheck } from "lucide-react";

import { formatSeconds } from "./format";

/**
 * Cevabın doğrulama özeti: kaç iddianın bir kaynağa bağlandığı, kaç belgeye dayandığı ve cevabın
 * ne kadar sürede geldiği. Kaynaksız cümleler backend'de cevaptan çıkarılır; sayısı da yazılır.
 * Backend şimdilik her cümlenin geçerli bir kaynağa bağlandığını denetler, anlamca karşılaştırmaz
 * (yargıç: #10); bu yüzden "doğrulandı" denmez.
 */
export default function VerificationStrip({
  claims,
  removed,
  documents,
  elapsedMs,
}: {
  claims: number;
  removed: number;
  documents: number;
  elapsedMs: number | null;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 font-mono text-xs text-graphite">
      <span
        title="Her cümle getirilen bir kaynak bölümüne bağlı; bağlanamayanlar çıkarıldı. Önemli konularda kaynağı açıp karşılaştır."
        className="inline-flex items-center gap-1.5 rounded-full border border-success/30 bg-success-soft px-2.5 py-1 font-medium text-success"
      >
        <ShieldCheck size={13} aria-hidden />
        {claims}/{claims} iddia kaynağa bağlı
      </span>
      {removed > 0 && <span>{removed} dayanaksız cümle çıkarıldı</span>}
      <span>{documents} belge</span>
      {elapsedMs != null && <span>cevap {formatSeconds(elapsedMs)}</span>}
    </div>
  );
}
