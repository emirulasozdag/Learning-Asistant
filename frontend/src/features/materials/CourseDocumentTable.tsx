import { Link } from "react-router";

import type { DocumentOut } from "../../api/types";
import { documentExtent, materialTotals, totalsHeading } from "../../labels";
import { formatRelative } from "../../text";
import FileBadge from "../../ui/FileBadge";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Ders dokümanları tablosu (OCW "Lecture Notes" tablosu gibi): aç, sayfa sayısı, AI Tutor'a sor. */
export default function CourseDocumentTable({
  documents,
  tutorPath,
}: {
  documents: DocumentOut[];
  /** Yalnızca öğrenci: satırdan AI Tutor'a geçiş. */
  tutorPath?: string;
}) {
  return (
    <Table label="Dokümanlar">
      <THead>
        <tr>
          <TH>Doküman</TH>
          <TH className="hidden text-right sm:table-cell">{totalsHeading(materialTotals(documents))}</TH>
          <TH className="hidden md:table-cell">Eklendi</TH>
          {tutorPath && (
            <TH className="text-right">
              <span className="sr-only">İşlem</span>
            </TH>
          )}
        </tr>
      </THead>
      <tbody>
        {documents.map((document) => (
          <TR key={document.id}>
            <TD>
              <div className="flex items-center gap-3">
                <FileBadge filename={document.filename} />
                <a href={document.file_url} target="_blank" rel="noreferrer" className="link text-md">
                  {document.title} ({document.filename.split(".").pop()?.toUpperCase()})
                </a>
              </div>
            </TD>
            <TD className="hidden text-right text-ink-2 tabular-nums sm:table-cell">
              {document.material_type === "video" ? documentExtent(document) : document.page_count}
            </TD>
            <TD className="hidden whitespace-nowrap text-graphite md:table-cell">
              {formatRelative(document.created_at)}
            </TD>
            {tutorPath && (
              <TD className="text-right">
                <Link to={tutorPath} className="link text-sm whitespace-nowrap">
                  AI Tutor'a sor
                </Link>
              </TD>
            )}
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
