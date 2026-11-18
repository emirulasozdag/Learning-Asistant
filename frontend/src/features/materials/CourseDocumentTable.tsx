import { PlayCircle } from "lucide-react";
import { Link } from "react-router";

import type { DocumentOut } from "../../api/types";
import { documentExtent, materialTotals, totalsHeading } from "../../labels";
import { formatRelative } from "../../text";
import FileBadge from "../../ui/FileBadge";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

/** Ders dokümanları tablosu (OCW "Lecture Notes" tablosu gibi): aç, sayfa sayısı, AI Tutor'a sor / izle. */
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
                <TitleLink document={document} watchPath={watchPath(document, tutorPath)} />
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
                {watchPath(document, tutorPath) ? (
                  // Video çalışma ekranında açılır; sorular durdurulan anla gider (#22, #103).
                  <Link to={watchPath(document, tutorPath)!} className="link text-sm whitespace-nowrap">
                    İzle ve sor
                  </Link>
                ) : (
                  <Link to={tutorPath} className="link text-sm whitespace-nowrap">
                    AI Tutor'a sor
                  </Link>
                )}
              </TD>
            )}
          </TR>
        ))}
      </tbody>
    </Table>
  );
}

/** Öğrenci için videonun çalışma ekranı; video değilse ya da oynatılamıyorsa yok. */
function watchPath(document: DocumentOut, tutorPath: string | undefined): string | undefined {
  if (!tutorPath || document.material_type !== "video" || !document.media_url) return undefined;
  return `${tutorPath.replace(/\/tutor$/, "")}/watch/${document.id}`;
}

/**
 * Başlık materyalin kendisini açar. Videoda bu altyazı dosyası (VTT) değil videodur: öğrenci
 * çalışma ekranına, eğitmen videonun adresine gider. Yalnızca transkripti olan video
 * (adres verilmemiş) transkript dosyasını açar ve böyle adlandırılır.
 */
function TitleLink({ document, watchPath }: { document: DocumentOut; watchPath: string | undefined }) {
  const video = document.material_type === "video";
  if (video && watchPath) {
    return (
      <>
        <VideoBadge />
        <Link to={watchPath} className="link text-md">
          {document.title}
        </Link>
      </>
    );
  }
  if (video && document.media_url) {
    return (
      <>
        <VideoBadge />
        <a href={document.media_url} target="_blank" rel="noreferrer" className="link text-md">
          {document.title}
        </a>
      </>
    );
  }
  return (
    <>
      <FileBadge filename={document.filename} />
      <a href={document.file_url} target="_blank" rel="noreferrer" className="link text-md">
        {document.title} ({video ? "transkript" : document.filename.split(".").pop()?.toUpperCase()})
      </a>
    </>
  );
}

function VideoBadge() {
  return (
    <span
      aria-hidden
      className="flex size-8 shrink-0 items-center justify-center rounded bg-surface text-graphite ring-1 ring-line"
    >
      <PlayCircle size={16} />
    </span>
  );
}
