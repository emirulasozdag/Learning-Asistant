import { BookOpen, Plus } from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useCourses } from "../../features/courses/context";
import { courseInitials } from "../../labels";
import { greeting } from "../../text";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageHeader, { SectionHeader } from "../../ui/PageHeader";
import { SkeletonRows } from "../../ui/Skeleton";

/**
 * Eğitmen ana sayfası — İLK SÜRÜM: karşılama + derslerim.
 * Ekip görevi (docs/UI_GOREVLERI.md): özet sayılar (öğrenci, soru, pratik) ve
 * "bu hafta en çok sorulan konular" — veri: dashboardService.instructorSummary().
 */
export default function InstructorDashboard() {
  const { user } = useAuth();
  const { courses, loading, error, openCreate } = useCourses();

  return (
    <div className="mx-auto max-w-6xl px-6 pt-8 pb-16 lg:px-10">
      <PageHeader
        title={`${greeting()}, ${user?.name ?? ""}`}
        description="Derslerinin bilgi tabanını buradan yönet; öğrencilerin AI Tutor'u yalnızca bu materyallerden cevap verir."
        actions={
          <Button variant="primary" icon={Plus} onClick={openCreate}>
            Ders oluştur
          </Button>
        }
      />

      <section className="mt-10">
        <SectionHeader title="Derslerim" />
        {loading ? (
          <SkeletonRows rows={2} />
        ) : error ? (
          <EmptyState
            icon={BookOpen}
            tone="danger"
            title="Dersler yüklenemedi"
            description={`API'ye ulaşılamıyor olabilir. (${error})`}
          />
        ) : courses.length === 0 ? (
          <div className="rounded-panel border border-dashed border-line-strong">
            <EmptyState
              icon={BookOpen}
              title="İlk dersini oluştur"
              description="Bir ders oluştur, notlarını yükle; öğrencilerin hemen soru sormaya başlayabilir."
              action={
                <Button variant="primary" icon={Plus} onClick={openCreate}>
                  Ders oluştur
                </Button>
              }
            />
          </div>
        ) : (
          <ul className="divide-y divide-line rounded-panel border border-line bg-surface">
            {courses.map((course) => (
              <li key={course.id}>
                <Link
                  to={`/instructor/courses/${course.id}`}
                  className="flex items-center gap-4 px-5 py-4 transition-colors hover:bg-canvas"
                >
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-panel bg-subtle text-sm font-semibold text-ink-2">
                    {courseInitials(course.name)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className="truncate text-md font-medium text-ink">{course.name}</span>
                      <Badge>{course.code}</Badge>
                    </span>
                    <span className="mt-0.5 block text-sm text-graphite">{course.stats.term}</span>
                  </span>
                  <span className="hidden text-right text-sm text-graphite sm:block">
                    <span className="block font-medium text-ink tabular-nums">
                      {course.stats.students}
                    </span>
                    öğrenci
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
