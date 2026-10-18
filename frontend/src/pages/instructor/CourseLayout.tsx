import { BookOpen } from "lucide-react";
import { Outlet, useParams } from "react-router";

import { useCourse, useCourses } from "../../features/courses/context";
import Badge from "../../ui/Badge";
import EmptyState from "../../ui/EmptyState";
import Skeleton from "../../ui/Skeleton";
import { RouteTabs } from "../../ui/Tabs";

/** Eğitmenin ders sayfası: ders başlığı + sekmeler (Genel bakış, Materyaller, ...). */
export default function CourseLayout() {
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  const { loading } = useCourses();

  if (!course && !loading) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Ders bulunamadı"
        description="Bu ders silinmiş ya da adres hatalı olabilir. Soldaki menüden bir ders seç."
        className="py-24"
      />
    );
  }

  const base = `/instructor/courses/${courseId}`;
  return (
    <div className="mx-auto max-w-6xl px-6 pt-8 pb-16 lg:px-10">
      <header className="mb-6">
        {course ? (
          <>
            <div className="flex items-center gap-2 text-sm text-graphite">
              <Badge>{course.code}</Badge>
              <span>{course.stats.term}</span>
              <span aria-hidden className="text-line-strong">
                /
              </span>
              <span>{course.stats.students} öğrenci</span>
            </div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-ink">{course.name}</h1>
          </>
        ) : (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-7 w-80" />
          </div>
        )}
      </header>
      <RouteTabs
        label="Ders bölümleri"
        tabs={[
          { to: `${base}/overview`, label: "Genel bakış", upcoming: true },
          { to: `${base}/materials`, label: "Materyaller" },
          { to: `${base}/students`, label: "Öğrenciler", upcoming: true },
          { to: `${base}/analytics`, label: "Analitik", upcoming: true },
        ]}
      />
      <div className="pt-8">
        <Outlet />
      </div>
    </div>
  );
}
