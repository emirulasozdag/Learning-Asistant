import { FolderOpen, ServerOff } from "lucide-react";
import { Link } from "react-router";

import type { DocumentOut, MaterialType } from "../../api/types";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import { MATERIAL_LABELS } from "../../labels";
import { formatRelative } from "../../text";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import FileBadge from "../../ui/FileBadge";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

const TYPE_ORDER: MaterialType[] = ["notes", "slides", "textbook", "past_exam", "transcript", "video"];

/** Öğrencinin ders materyalleri: türe göre gruplanmış tablolar (OCW "Lecture Notes" gibi). */
export default function CourseMaterialsPage() {
  const { course, documents, documentsFailed, reloadDocuments } = useCourseOutlet();

  return (
    <div>
      <PageTitle
        title="Ders materyalleri"
        description="AI Tutor bu dersteki sorulara yalnızca buradaki dokümanlardan cevap verir."
      />
      {documentsFailed ? (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Materyaller yüklenemedi"
          description="Ders materyaline şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={<Button onClick={reloadDocuments}>Tekrar dene</Button>}
        />
      ) : documents === null ? (
        <SkeletonRows rows={3} />
      ) : documents.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="Henüz materyal yok"
          description="Eğitmen ders notlarını yüklediğinde burada listelenecek."
        />
      ) : (
        <div className="flex flex-col gap-10">
          {TYPE_ORDER.map((type) => {
            const ofType = documents.filter((d) => d.material_type === type);
            if (ofType.length === 0) return null;
            return (
              <section key={type}>
                <h2 className="mb-3 text-lg font-bold text-ink">{MATERIAL_LABELS[type]}</h2>
                <MaterialTable documents={ofType} tutorPath={`/student/courses/${course.id}/tutor`} />
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}

function MaterialTable({ documents, tutorPath }: { documents: DocumentOut[]; tutorPath: string }) {
  return (
    <Table label="Dokümanlar">
      <THead>
        <tr>
          <TH>Doküman</TH>
          <TH className="hidden text-right sm:table-cell">Sayfa</TH>
          <TH className="hidden md:table-cell">Eklendi</TH>
          <TH className="text-right">
            <span className="sr-only">İşlem</span>
          </TH>
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
            <TD className="hidden text-right text-ink-2 tabular-nums sm:table-cell">{document.page_count}</TD>
            <TD className="hidden whitespace-nowrap text-graphite md:table-cell">
              {formatRelative(document.created_at)}
            </TD>
            <TD className="text-right">
              <Link to={tutorPath} className="link text-sm whitespace-nowrap">
                AI Tutor'a sor
              </Link>
            </TD>
          </TR>
        ))}
      </tbody>
    </Table>
  );
}
