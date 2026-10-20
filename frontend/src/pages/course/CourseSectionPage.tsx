import { ServerOff, Upload } from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import type { MaterialSection } from "../../features/courses/sections";
import CourseDocumentTable from "../../features/materials/CourseDocumentTable";
import { sortByTitle } from "../../features/materials/sortByTitle";
import { MATERIAL_LABELS } from "../../labels";
import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";

/** Materyal türlerine göre dolan bir ders bölümü (OCW "Lecture Notes", "Quizzes"… sayfası). */
export default function CourseSectionPage({ section }: { section: MaterialSection }) {
  const { user } = useAuth();
  const { course, documents, documentsFailed, reloadDocuments } = useCourseOutlet();
  const instructor = user?.role === "instructor";
  const base = `/${user?.role ?? "student"}/courses/${course.id}`;
  const tutorPath = instructor ? undefined : `${base}/tutor`;

  const groups = section.types
    .map((type) => ({ type, documents: sortByTitle((documents ?? []).filter((d) => d.material_type === type)) }))
    .filter((group) => group.documents.length > 0);

  return (
    <div>
      <PageTitle
        title={section.label}
        description={section.description}
        actions={
          instructor && (
            <Link to={`${base}/materials`} className={buttonClasses("secondary")}>
              <Upload size={16} aria-hidden />
              Materyal ekle
            </Link>
          )
        }
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
      ) : groups.length === 0 ? (
        <EmptyState icon={section.icon} title={section.empty} />
      ) : groups.length === 1 ? (
        <CourseDocumentTable documents={groups[0].documents} tutorPath={tutorPath} />
      ) : (
        <div className="flex flex-col gap-10">
          {groups.map((group) => (
            <section key={group.type}>
              <h2 className="mb-3 text-lg font-bold text-ink">{MATERIAL_LABELS[group.type]}</h2>
              <CourseDocumentTable documents={group.documents} tutorPath={tutorPath} />
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
