import { BookOpen, ServerOff } from "lucide-react";
import { Fragment, useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import AskBox from "../../features/courses/AskBox";
import { useCourses } from "../../features/courses/context";
import { useMaterialSummaries, type MaterialSummary } from "../../features/courses/useMaterialSummaries";
import { courseMetaParts } from "../../labels";
import type { Course } from "../../services/courseService";
import { greeting } from "../../text";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import Skeleton, { SkeletonRows } from "../../ui/Skeleton";

/** Öğrenci ana sayfası: soru kutusu ve kayıtlı dersler (katalog listesi). */
export default function StudentDashboard() {
  const { user } = useAuth();
  const { courses, loading, error, refresh } = useCourses();
  const summaries = useMaterialSummaries(courses);
  const [retrying, setRetrying] = useState(false);
  const firstName = user?.name.split(" ")[0] ?? "";

  async function retry() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-[72rem] px-5 py-10 sm:px-8 lg:px-10">
          <p className="text-md text-graphite">
            {greeting()}, {firstName}
          </p>
          <h1 className="mt-1 text-[2.25rem] leading-tight font-bold tracking-tight text-ink">
            Ders materyaline soru sor
          </h1>
          <p className="mt-2 max-w-2xl text-md text-ink-2">
            Cevaplar yalnızca dersinin materyaline dayanır ve dayandığı sayfayla birlikte gelir.
          </p>
          {courses.length > 0 && (
            <div className="mt-6 max-w-3xl">
              <AskBox courses={courses} />
            </div>
          )}
        </div>
      </section>

      <div className="page">
        <PageTitle title="Derslerim" />
        {loading ? (
          <SkeletonRows rows={3} />
        ) : error ? (
          <EmptyState
            icon={ServerOff}
            tone="danger"
            title="Dersler yüklenemedi"
            description="Ders listesine şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
            action={
              <Button loading={retrying} onClick={() => void retry()}>
                Tekrar dene
              </Button>
            }
          />
        ) : courses.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="Henüz kayıtlı dersin yok"
            description="Eğitmenin dersi oluşturduğunda burada görünecek."
          />
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {courses.map((course) => (
              <li key={course.id}>
                <CourseRow course={course} summary={summaries[course.id]} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

/** Katalog satırı: "BLM2512 | Güz 2026 | Lisans", ders adı bağlantısı, eğitmen ve kapsam. */
function CourseRow({ course, summary }: { course: Course; summary: MaterialSummary | null | undefined }) {
  const base = `/student/courses/${course.id}`;
  return (
    <div className="flex flex-col gap-4 py-6 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center text-sm font-semibold text-graphite">
          {courseMetaParts(course).map((part, index) => (
            <Fragment key={part}>
              {index > 0 && <span aria-hidden className="mx-2 h-3.5 w-px bg-line-strong" />}
              {part}
            </Fragment>
          ))}
        </p>
        <h2 className="mt-1.5 text-xl font-bold tracking-tight">
          <Link to={base} className="text-ink hover:text-link hover:underline hover:underline-offset-4">
            {course.name}
          </Link>
        </h2>
        <p className="mt-1.5 text-base text-graphite">
          {course.instructor_name && <>{course.instructor_name} &nbsp;/&nbsp; </>}
          {summary === undefined ? (
            <Skeleton className="inline-block h-3.5 w-32 align-middle" />
          ) : summary === null ? (
            "Materyal bilgisi alınamadı"
          ) : summary.documents === 0 ? (
            "Henüz materyal yüklenmedi"
          ) : (
            `${summary.documents} doküman, ${summary.pages} sayfa`
          )}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-5 text-base">
        <Link to={`${base}/materials`} className="link">
          Materyaller
        </Link>
        <Link to={`${base}/tutor`} className="link font-semibold">
          AI Tutor'a sor
        </Link>
      </div>
    </div>
  );
}
