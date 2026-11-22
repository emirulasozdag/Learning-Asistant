import { BookOpen, ChevronRight, FolderOpen, Plus, ServerOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useCourses } from "../../features/courses/context";
import { useCourseActivities } from "../../features/courses/useCourseActivities";
import { useMaterialSummaries, type MaterialSummary } from "../../features/courses/useMaterialSummaries";
import { describeTotals } from "../../labels";
import type { Course } from "../../services/courseService";
import { formatRelative, formatTime, firstName, greeting } from "../../text";
import Button from "../../ui/Button";
import Card from "../../ui/Card";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import Skeleton, { SkeletonRows } from "../../ui/Skeleton";
import StatRow from "../../ui/StatRow";
import { buttonClasses } from "../../ui/buttonStyles";

const CODE_CHIP = "rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent";

/** Eğitmen ana sayfası: dersler, bilgi tabanlarının durumu ve öğrenci etkinliği (gerçek veri). */
export default function InstructorDashboard() {
  const { user } = useAuth();
  const { courses, loading, error, refresh, openCreate } = useCourses();
  const summaries = useMaterialSummaries(courses);
  const activities = useCourseActivities(courses);
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  const known = courses.map((course) => summaries[course.id]).filter((s): s is MaterialSummary => Boolean(s));
  const totalsReady = courses.length > 0 && known.length === courses.length;
  // Tüm derslerde materyalde dayanağı bulunamayan en yeni sorular: "neyi eklemeliyim" listesi.
  const gaps = courses
    .flatMap((course) =>
      (activities[course.id]?.unanswered_questions ?? []).map((item) => ({ ...item, course })),
    )
    .sort((a, b) => b.asked_at.localeCompare(a.asked_at))
    .slice(0, 5);

  return (
    <div className="page flex flex-col gap-10">
      <section>
        <p className="text-md text-graphite">
          {greeting()}, {firstName(user?.name)}
        </p>
        <PageTitle
          className="mt-1"
          title="Derslerim"
          description="AI Tutor öğrencilere yalnızca yüklediğin materyalden cevap verir."
          actions={
            <Button variant="primary" icon={Plus} onClick={openCreate}>
              Ders oluştur
            </Button>
          }
        />

        {totalsReady && (
          <StatRow
            className="mb-8"
            stats={[
              { label: "Ders", value: courses.length },
              { label: "Doküman", value: known.reduce((sum, s) => sum + s.documents, 0) },
              ...(known.some((s) => s.totals.hasPages)
                ? [{ label: "Sayfa", value: known.reduce((sum, s) => sum + s.totals.pages, 0) }]
                : []),
              ...(known.some((s) => s.totals.hasVideo)
                ? [
                    {
                      label: "Video süresi",
                      value: formatTime(known.reduce((sum, s) => sum + s.totals.videoSeconds, 0)),
                    },
                  ]
                : []),
              {
                label: "Öğrenci sorusu",
                value: courses.reduce((sum, course) => sum + (activities[course.id]?.questions ?? 0), 0),
                // Sıfır "soru yok" demek olmayabilir: yalnızca kaydı açık, en az üç öğrenci sayılır (#105).
                hint: "araştırma kaydı açık olanlar",
              },
            ]}
          />
        )}

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
            title="İlk dersini oluştur"
            description="Dersi oluştur ve notlarını yükle; öğrencilerin hemen soru sormaya başlayabilir."
            action={
              <Button variant="primary" icon={Plus} onClick={openCreate}>
                Ders oluştur
              </Button>
            }
          />
        ) : (
          <ul aria-label="Derslerim" className="flex flex-col gap-3">
            {courses.map((course) => (
              <CourseItem
                key={course.id}
                course={course}
                summary={summaries[course.id]}
                questions={activities[course.id]?.questions}
              />
            ))}
          </ul>
        )}
      </section>

      {gaps.length > 0 && (
        <section>
          <PageTitle
            level={2}
            title="Materyalde bulunamayan son sorular"
            description="Öğrencilerin sorduğu ama ders materyalinde dayanağı olmayan konular. Bu konular için materyal eklemeyi düşünebilirsin."
          />
          <ul className="flex flex-col gap-2">
            {gaps.map((gap, index) => (
              <li key={`${gap.course.id}-${gap.asked_at}-${index}`}>
                <Card padding="none" interactive>
                  <Link
                    to={`/instructor/courses/${gap.course.id}/activity`}
                    className="group flex items-center gap-4 px-4 py-3"
                  >
                    <span className={CODE_CHIP}>{gap.course.code}</span>
                    <p className="min-w-0 flex-1 truncate text-base text-ink">{gap.question}</p>
                    <span className="hidden shrink-0 text-sm text-graphite sm:block">
                      {formatRelative(gap.asked_at)}
                    </span>
                    <ChevronRight size={16} aria-hidden className="shrink-0 text-faint group-hover:text-accent" />
                  </Link>
                </Card>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Ders kartı: kod, ad bağlantısı, dönem ve materyal özeti, soru sayısı ve "Materyaller". */
function CourseItem({
  course,
  summary,
  questions,
}: {
  course: Course;
  summary: MaterialSummary | null | undefined;
  questions: number | undefined;
}) {
  const base = `/instructor/courses/${course.id}`;
  return (
    <Card as="li" className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className={CODE_CHIP}>{course.code}</span>
          {course.term && <span className="text-sm text-graphite">{course.term}</span>}
        </div>
        <h2 className="mt-2 text-lg font-bold tracking-tight">
          <Link to={base} className="text-ink hover:text-link hover:underline hover:underline-offset-4">
            {course.name}
          </Link>
        </h2>
        <p className="mt-1 text-sm text-graphite">
          {summary === undefined ? (
            <Skeleton className="inline-block h-3.5 w-32 align-middle" />
          ) : summary === null ? (
            "Materyal bilgisi alınamadı"
          ) : summary.documents === 0 ? (
            <span className="text-warning">Materyal yok; öğrenciler soru soramaz</span>
          ) : (
            [`${summary.documents} doküman`, describeTotals(summary.totals)].filter(Boolean).join(", ")
          )}
          {questions !== undefined && questions > 0 && (
            <span className="tabular-nums"> &nbsp;/&nbsp; {questions} soru</span>
          )}
        </p>
      </div>
      <Link to={`${base}/materials`} className={buttonClasses("secondary", "sm")}>
        <FolderOpen size={14} aria-hidden />
        Materyaller
      </Link>
    </Card>
  );
}
