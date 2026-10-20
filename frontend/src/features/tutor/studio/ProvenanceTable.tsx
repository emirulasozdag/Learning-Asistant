import type { DocumentOut, SourceDetail } from "../../../api/types";
import type { Course } from "../../../services/courseService";
import { formatTimeRange } from "../../../text";

const DATE = new Intl.DateTimeFormat("tr-TR", { day: "2-digit", month: "2-digit", year: "numeric" });

/**
 * Kaynağın künyesi (teknik çizimdeki antet gibi): hangi dersin hangi belgesi, hangi sayfa ya da
 * an, kim onayladı. Materyali yalnızca dersin eğitmeni yükler ve yükleme onay sayılır, bu yüzden
 * onay tarihi belgenin yüklendiği gündür.
 */
export default function ProvenanceTable({
  course,
  source,
  document,
}: {
  course: Course;
  source: SourceDetail;
  document: DocumentOut | undefined;
}) {
  const where =
    source.page != null
      ? { label: "Sayfa", value: document?.page_count ? `${source.page} / ${document.page_count}` : `${source.page}` }
      : source.t_start != null
        ? { label: "Zaman", value: formatTimeRange(source.t_start, source.t_end) }
        : null;

  const cells: { label: string; value: string; wide?: boolean }[] = [
    { label: "Ders", value: course.code },
    { label: "Belge", value: source.document_title },
    ...(where ? [where] : []),
    { label: "Onaylayan", value: course.instructor_name ?? "Ders eğitmeni", wide: true },
    { label: "Onay", value: document ? DATE.format(new Date(document.created_at)) : "Onaylı materyal" },
  ];

  return (
    <dl className="grid grid-cols-3 overflow-hidden rounded-[3px] border border-line-strong font-mono text-xs">
      {cells.map((cell) => (
        <div
          key={cell.label}
          className={`-mt-px -ml-px border-t border-l border-line-strong px-2.5 py-1.5 ${cell.wide ? "col-span-2" : ""}`}
        >
          <dt className="text-graphite">{cell.label}</dt>
          <dd className="truncate font-semibold text-ink">{cell.value}</dd>
        </div>
      ))}
    </dl>
  );
}
