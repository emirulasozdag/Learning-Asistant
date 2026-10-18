import type { IngestionReport as Report } from "../../api/types";

interface Step {
  title: string;
  value: string;
  detail: string;
  ms: number;
}

function steps(report: Report): Step[] {
  const removed = report.repeated_lines_removed + report.page_numbers_removed;
  return [
    {
      title: "Okuma",
      value: `${report.pages_read} sayfa`,
      detail: report.empty_pages ? `${report.empty_pages} boş sayfa atlandı` : "metin çıkarıldı",
      ms: report.timings_ms.parse,
    },
    {
      title: "Temizleme",
      value: `${removed} satır`,
      detail: `${report.repeated_lines_removed} üst/alt bilgi, ${report.page_numbers_removed} sayfa no.`,
      ms: report.timings_ms.clean,
    },
    {
      title: "Parçalama",
      value: `${report.chunks} parça`,
      detail: "her parça tek sayfadan",
      ms: report.timings_ms.chunk,
    },
    {
      title: "Vektörleştirme",
      value: `${report.vectors} vektör`,
      detail: `${report.vector_dim} boyut, ${report.embedding_model.split("/").pop()}`,
      ms: report.timings_ms.embed,
    },
  ];
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)} sn` : `${ms} ms`;
}

/** Yükleme hattı: dosyanın hangi adımlardan geçip aranabilir hale geldiği. */
export default function IngestionReport({ report }: { report: Report }) {
  const total = Object.values(report.timings_ms).reduce((sum, ms) => sum + ms, 0);
  return (
    <section aria-label="Yükleme raporu">
      <div className="mb-3 flex items-baseline justify-between gap-4">
        <h3 className="text-base font-medium text-ink">Bilgi tabanına nasıl eklendi</h3>
        <span className="text-sm text-graphite tabular-nums">toplam {formatMs(total)}</span>
      </div>
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
            <p className="mt-1.5 text-xs text-faint tabular-nums">{formatMs(step.ms)}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
