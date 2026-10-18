import { BookOpen, MessageSquareText } from "lucide-react";
import { Link } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { useCourses } from "../../features/courses/context";
import { greeting } from "../../text";
import Badge from "../../ui/Badge";
import { buttonClasses } from "../../ui/buttonStyles";
import EmptyState from "../../ui/EmptyState";
import PageHeader, { SectionHeader } from "../../ui/PageHeader";
import { SkeletonRows } from "../../ui/Skeleton";

/**
 * Öğrenci ana sayfası — İLK SÜRÜM: karşılama + derslerim (AI Tutor'a hızlı geçiş).
 * Ekip görevi (docs/UI_GOREVLERI.md): "Kaldığın yerden devam et", son sorular ve
 * pratik ilerlemesi — veri: dashboardService.recentQuestions(), practiceProgress().
 */
export default function StudentDashboard() {
  const { user } = useAuth();
  const { courses, loading, error } = useCourses();
  const firstName = user?.name.split(" ")[0] ?? "";

  return (
    <div className="mx-auto max-w-5xl px-6 pt-8 pb-16 lg:px-10">
      <PageHeader
        title={`${greeting()}, ${firstName}`}
        description="Derslerinin notlarına soru sor; her cevap dayandığı sayfayla birlikte gelir."
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
          <EmptyState
            icon={BookOpen}
            title="Henüz kayıtlı dersin yok"
            description="Eğitmenin dersi oluşturduğunda burada görünecek."
          />
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {courses.map((course) => (
              <li
                key={course.id}
                className="flex flex-col rounded-panel border border-line bg-surface p-5 transition-colors hover:border-line-strong"
              >
                <div className="flex items-center gap-2 text-sm text-graphite">
                  <Badge>{course.code}</Badge>
                  {course.stats.term}
                </div>
                <p className="mt-3 text-md font-semibold text-ink">{course.name}</p>
                <div className="mt-5 flex items-center justify-between gap-3">
                  <span className="text-sm text-graphite">Ders materyalinden kaynaklı cevaplar</span>
                  <Link
                    to={`/student/courses/${course.id}/tutor`}
                    className={buttonClasses("primary", "sm")}
                  >
                    <MessageSquareText size={14} aria-hidden />
                    AI Tutor'u aç
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
