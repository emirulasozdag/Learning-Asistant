import type { IngestionReport as Report } from "../../api/types";

interface Step {
  title: string;
  value: string;
  detail: string;
}

/** Eğitmenin göreceği sade adımlar; model, vektör boyutu ve süreler "Teknik ayrıntılar"da. */
function steps(report: Report): Step[] {
  const removed = report.repeated_lines_removed + report.page_numbers_removed;
  const video = report.cues_read != null;
  return [
    {
      title: "Okuma",
      value: video ? `${report.cues_read} altyazı satırı` : `${report.pages_read} sayfa`,
      detail: video
        ? report.cues_skipped
          ? `${report.cues_skipped} bozuk satır atlandı`
          : "metin çıkarıldı"
        : report.empty_pages
          ? `${report.empty_pages} boş sayfa atlandı`
          : "metin çıkarıldı",
    },
    {
      title: "Temizleme",
      value: `${removed} satır kaldırıldı`,
      detail: `${report.repeated_lines_removed} üst/alt bilgi, ${report.page_numbers_removed} sayfa numarası`,
    },
    {
      title: "Bölümlere ayırma",
      value: `${report.chunks} bölüm`,
      detail: video ? "ardışık satırlar, zaman aralığıyla" : "her bölüm tek sayfadan",
    },
    {
      title: "Aramaya hazırlama",
      value: "Hazır",
      detail: "öğrenci soruları bu bölümlerde aranır",
    },
  ];
}

const TIMING_LABELS: Record<keyof Report["timings_ms"], string> = {
  parse: "Okuma",
  clean: "Temizleme",
  chunk: "Bölümlere ayırma",
  embed: "Aramaya hazırlama",
};

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} sn` : `${ms} ms`;
}

/** Yükleme hattı: dosyanın hangi adımlardan geçip aranabilir hale geldiği. */
export default function IngestionReport({ report }: { report: Report }) {
  const total = Object.values(report.timings_ms).reduce((sum, ms) => sum + ms, 0);
  return (
    <section aria-label="Yükleme raporu">
      <h3 className="mb-3 text-base font-semibold text-ink">Bilgi tabanına nasıl eklendi</h3>
      <ol className="grid grid-cols-2 gap-px overflow-hidden rounded-panel border border-line bg-line sm:grid-cols-4">
        {steps(report).map((step, index) => (
          <li
            key={step.title}
            className="step-reveal bg-surface px-3 py-3"
            style={{ animationDelay: `${index * 140}ms` }}
          >
            <p className="text-xs text-graphite">
              {index + 1}. {step.title}
            </p>
            <p className="mt-1 text-md font-semibold text-ink tabular-nums">{step.value}</p>
            <p className="mt-0.5 text-xs text-graphite">{step.detail}</p>
          </li>
        ))}
      </ol>
      {report.warnings.length > 0 && (
        <ul className="mt-2 text-sm text-graphite">
          {report.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm text-graphite hover:text-ink">Teknik ayrıntılar</summary>
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-6 gap-y-1 text-sm">
          <dt className="text-graphite">Embedding modeli</dt>
          <dd className="break-all text-ink">{report.embedding_model}</dd>
          <dt className="text-graphite">Vektör</dt>
          <dd className="text-ink tabular-nums">
            {report.vectors} adet, {report.vector_dim} boyut
          </dd>
          {(Object.keys(TIMING_LABELS) as (keyof Report["timings_ms"])[]).map((key) => (
            <div key={key} className="contents">
              <dt className="text-graphite">{TIMING_LABELS[key]} süresi</dt>
              <dd className="text-ink tabular-nums">{formatMs(report.timings_ms[key])}</dd>
            </div>
          ))}
          <dt className="text-graphite">Toplam süre</dt>
          <dd className="text-ink tabular-nums">{formatMs(total)}</dd>
        </dl>
      </details>
    </section>
  );
}
