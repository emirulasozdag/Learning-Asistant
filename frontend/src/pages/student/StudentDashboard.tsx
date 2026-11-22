import { BookOpen, FolderOpen, MessageSquareText, ServerOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import AskBox from "../../features/courses/AskBox";
import JoinCourseForm from "../../features/courses/JoinCourseForm";
import { useCourses } from "../../features/courses/context";
import { useMaterialSummaries, type MaterialSummary } from "../../features/courses/useMaterialSummaries";
import { courseMetaParts, describeTotals } from "../../labels";
import type { Course } from "../../services/courseService";
import { firstName, greeting } from "../../text";
import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import Card from "../../ui/Card";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import Skeleton, { SkeletonRows } from "../../ui/Skeleton";
import { usePageTitle } from "../../ui/usePageTitle";

/** Öğrenci ana sayfası: soru kutusu ve kayıtlı dersler. */
export default function StudentDashboard() {
  const { user } = useAuth();
  const { courses, loading, error, refresh } = useCourses();
  const summaries = useMaterialSummaries(courses);
  const [retrying, setRetrying] = useState(false);
  usePageTitle("Derslerim");

  async function retry() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  return (
    <>
      <section className="border-b border-line bg-surface">
        <div className="mx-auto max-w-[76rem] px-5 py-10 sm:px-8 lg:py-12">
          <p className="text-md text-graphite">
            {greeting()}, {firstName(user?.name)}
          </p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight text-balance text-ink">
            Ders materyaline soru sor
          </h1>
          <p className="mt-3 max-w-2xl text-md text-ink-2">
            Cevaplar yalnızca dersinin materyaline dayanır ve dayandığı sayfayla birlikte gelir.
          </p>
          {courses.length > 0 && (
            <div className="mt-6 max-w-3xl">
              <AskBox courses={courses} />
            </div>
          )}
        </div>
      </section>

      <div className="page flex flex-col gap-10">
        <section>
          <PageTitle level={2} title="Derslerim" />
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
              description="Eğitmeninden dersin katılım kodunu iste ve aşağıya gir."
              action={<JoinCourseForm />}
            />
          ) : (
            <ul className="grid gap-4 lg:grid-cols-2">
              {courses.map((course) => (
                <CourseCard key={course.id} course={course} summary={summaries[course.id]} />
              ))}
            </ul>
          )}
        </section>

        {!loading && !error && courses.length > 0 && (
          <section aria-labelledby="join-heading">
            <h2 id="join-heading" className="mb-3 text-lg font-bold text-ink">
              Başka bir derse katıl
            </h2>
            <JoinCourseForm />
          </section>
        )}
      </div>
    </>
  );
}

/** Ders kartı: ders kodu, ad bağlantısı, eğitmen ve materyal özeti, iki eylem. */
function CourseCard({ course, summary }: { course: Course; summary: MaterialSummary | null | undefined }) {
  const base = `/student/courses/${course.id}`;
  const [code, ...meta] = courseMetaParts(course);
  return (
    <Card as="li" className="flex flex-col gap-4">
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-graphite">
          <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent">{code}</span>
          {meta.length > 0 && <span>{meta.join(" · ")}</span>}
        </p>
        <h3 className="mt-2 text-lg font-bold tracking-tight">
          <Link to={base} className="text-ink hover:text-link hover:underline hover:underline-offset-4">
            {course.name}
          </Link>
        </h3>
        <p className="mt-1 text-sm text-graphite">
          {course.instructor_name && <>{course.instructor_name} · </>}
          {summary === undefined ? (
            <Skeleton className="inline-block h-3.5 w-32 align-middle" />
          ) : summary === null ? (
            "Materyal bilgisi alınamadı"
          ) : summary.documents === 0 ? (
            "Henüz materyal yüklenmedi"
          ) : (
            [`${summary.documents} doküman`, describeTotals(summary.totals)].filter(Boolean).join(", ")
          )}
        </p>
      </div>
      <div className="mt-auto flex flex-wrap items-center gap-2">
        <Link to={`${base}/materials`} className={buttonClasses("secondary", "sm")}>
          <FolderOpen size={14} aria-hidden />
          Materyaller
        </Link>
        <Link to={`${base}/tutor`} className={buttonClasses("primary", "sm")}>
          <MessageSquareText size={14} aria-hidden />
          AI Tutor'a sor
        </Link>
      </div>
    </Card>
  );
}
