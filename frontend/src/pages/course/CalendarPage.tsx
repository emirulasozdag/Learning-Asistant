import { CalendarDays, ServerOff } from "lucide-react";

import type { DocumentOut } from "../../api/types";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Haftalık takvim (OCW "Calendar"); dokümanı yüklenmiş satırlar dokümana bağlanır. */
export default function CalendarPage() {
  const { outline, outlineFailed, documents } = useCourseOutlet();
  const calendar = outline?.calendar;
  const byLabel = documentsByLabel(documents ?? []);

  return (
    <div>
      <PageTitle title="Takvim" description={calendar?.intro ?? "Haftalara göre dersler, uygulamalar ve önemli tarihler."} />
      {outlineFailed ? (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Takvim yüklenemedi"
          description="Ders bilgisine şu an ulaşılamıyor. Sayfayı yenileyip tekrar dene."
        />
      ) : outline === null ? (
        <SkeletonRows rows={6} />
      ) : !calendar?.rows.length ? (
        <EmptyState icon={CalendarDays} title="Bu derse henüz takvim eklenmedi." />
      ) : (
        <Table label="Ders takvimi">
          <THead>
            <tr>
              {calendar.columns.map((column, index) => (
                <TH key={index}>{column}</TH>
              ))}
            </tr>
          </THead>
          <tbody>
            {calendar.rows.map((row, rowIndex) => (
              <TR key={rowIndex}>
                {row.map((cell, index) => (
                  <TD
                    key={index}
                    colSpan={cell.span > 1 ? cell.span : undefined}
                    className={index === 0 ? "w-16 align-top font-semibold text-ink tabular-nums" : "align-top"}
                  >
                    <ul className="flex flex-col gap-1">
                      {cell.lines.map((line, lineIndex) => {
                        const document = byLabel.get(label(line));
                        return (
                          // Kısa satırlar ("Recitation 1") bölünmez; uzun ders başlıkları sarılır.
                          <li key={lineIndex} className={line.length <= 24 ? "whitespace-nowrap" : undefined}>
                            {document ? (
                              <a href={document.file_url} target="_blank" rel="noreferrer" className="link">
                                {line}
                              </a>
                            ) : (
                              line
                            )}
                          </li>
                        );
                      })}
                    </ul>
                  </TD>
                ))}
              </TR>
            ))}
          </tbody>
        </Table>
      )}
    </div>
  );
}

/**
 * Takvim satırını doküman başlığıyla eşleştirme anahtarı: iki noktadan önceki kısım, sondaki
 * "Due" atılarak. "Lecture 18: Dynamic Programming…" ve "Lecture 18: Pseudopolynomial" → "lecture 18";
 * "Problem Set 0 Due" → "problem set 0".
 */
function label(text: string): string {
  return text
    .split(":")[0]
    .replace(/\s+due$/i, "")
    .trim()
    .toLocaleLowerCase("en");
}

/** Anahtarı tek bir dokümana karşılık gelenler (belirsiz eşleşmeler bağlanmaz). */
function documentsByLabel(documents: DocumentOut[]): Map<string, DocumentOut> {
  const map = new Map<string, DocumentOut>();
  const ambiguous = new Set<string>();
  for (const document of documents) {
    const key = label(document.title);
    if (map.has(key)) ambiguous.add(key);
    map.set(key, document);
  }
  for (const key of ambiguous) map.delete(key);
  return map;
}
