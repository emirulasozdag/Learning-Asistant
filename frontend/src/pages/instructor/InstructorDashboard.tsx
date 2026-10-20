import { BookOpen, ChevronRight, Plus, ServerOff } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useCourses } from "../../features/courses/context";
import { useCourseActivities } from "../../features/courses/useCourseActivities";
import { useMaterialSummaries, type MaterialSummary } from "../../features/courses/useMaterialSummaries";
import { compactTotals } from "../../labels";
import type { Course } from "../../services/courseService";
import { formatRelative, formatTime, greeting } from "../../text";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import PageTitle from "../../ui/PageTitle";
import Skeleton, { SkeletonRows } from "../../ui/Skeleton";
import StatRow from "../../ui/StatRow";
import { Table, TD, TH, THead, TR } from "../../ui/Table";

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
    <div className="page">
      <p className="text-md text-graphite">
        {greeting()}, {user?.name}
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
          className="mb-10"
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
        <Table label="Derslerim">
          <THead>
            <tr>
              <TH>Kod</TH>
              <TH>Ders</TH>
              <TH className="hidden md:table-cell">Dönem</TH>
              <TH className="hidden text-right sm:table-cell">Doküman</TH>
              <TH className="hidden text-right lg:table-cell">Sayfa / süre</TH>
              <TH className="text-right">Soru</TH>
            </tr>
          </THead>
          <tbody>
            {courses.map((course) => (
              <CourseRow
                key={course.id}
                course={course}
                summary={summaries[course.id]}
                questions={activities[course.id]?.questions}
              />
            ))}
          </tbody>
        </Table>
      )}

      {gaps.length > 0 && (
        <section className="mt-12">
          <PageTitle
            title="Materyalde bulunamayan son sorular"
            description="Öğrencilerin sorduğu ama ders materyalinde dayanağı olmayan konular. Bu konular için materyal eklemeyi düşünebilirsin."
          />
          <ul className="divide-y divide-line border-y border-line">
            {gaps.map((gap, index) => (
              <li key={`${gap.course.id}-${gap.asked_at}-${index}`}>
                <Link
                  to={`/instructor/courses/${gap.course.id}/activity`}
                  className="group flex items-center gap-4 py-3.5 transition-colors hover:bg-surface"
                >
                  <Badge>{gap.course.code}</Badge>
                  <p className="min-w-0 flex-1 truncate text-md text-ink">{gap.question}</p>
                  <span className="hidden shrink-0 text-sm text-graphite sm:block">
                    {formatRelative(gap.asked_at)}
                  </span>
                  <ChevronRight size={16} aria-hidden className="shrink-0 text-faint group-hover:text-accent" />
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function CourseRow({
  course,
  summary,
  questions,
}: {
  course: Course;
  summary: MaterialSummary | null | undefined;
  questions: number | undefined;
}) {
  const number = (value: number | undefined | null) =>
    value === undefined ? <Skeleton className="ml-auto h-3.5 w-6" /> : (value ?? "—");
  return (
    <TR>
      <TD className="font-semibold whitespace-nowrap text-ink-2">{course.code}</TD>
      <TD>
        <Link to={`/instructor/courses/${course.id}`} className="link text-md font-medium">
          {course.name}
        </Link>
        {summary?.documents === 0 && (
          <span className="block text-sm text-warning">Materyal yok; öğrenciler soru soramaz</span>
        )}
      </TD>
      <TD className="hidden whitespace-nowrap text-graphite md:table-cell">{course.term ?? "—"}</TD>
      <TD className="hidden text-right tabular-nums sm:table-cell">
        {number(summary === null ? null : summary?.documents)}
      </TD>
      <TD className="hidden text-right tabular-nums lg:table-cell">
        {summary ? compactTotals(summary.totals) : number(summary === null ? null : undefined)}
      </TD>
      <TD className="text-right tabular-nums">{number(questions)}</TD>
    </TR>
  );
}
