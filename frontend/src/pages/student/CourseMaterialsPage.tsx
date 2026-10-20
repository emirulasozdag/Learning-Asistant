import { FolderOpen, ServerOff } from "lucide-react";

import { useCourseOutlet } from "../../features/courses/courseOutlet";
import CourseDocumentTable from "../../features/materials/CourseDocumentTable";
import { sortByTitle } from "../../features/materials/sortByTitle";
import { MATERIAL_LABELS, TYPE_ORDER } from "../../labels";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";

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
                <CourseDocumentTable
                  documents={sortByTitle(ofType)}
                  tutorPath={`/student/courses/${course.id}/tutor`}
                />
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
