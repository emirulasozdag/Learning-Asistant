import { BarChart3, BookOpen, FolderOpen, Info, LayoutList, MessageSquareText, ServerOff } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router";

import type { DocumentOut } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { useCourse, useCourses } from "../features/courses/context";
import type { CourseOutlet } from "../features/courses/courseOutlet";
import { LEVEL_LABELS, MATERIAL_LABELS, courseMetaParts, languageLabel, materialTotals } from "../labels";
import { courseService, type Course } from "../services/courseService";
import { formatRelative, formatTime } from "../text";
import Button from "../ui/Button";
import { cx } from "../ui/cx";
import EmptyState from "../ui/EmptyState";
import InfoPanel, { type InfoSection } from "../ui/InfoPanel";
import { SectionNav, SectionTabs, type SectionLink } from "../ui/SectionNav";
import Skeleton from "../ui/Skeleton";
import { coursePath } from "./navigation";

const INFO_KEY = "la.courseInfo.closed";

function readInfoClosed(): boolean {
  try {
    return localStorage.getItem(INFO_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * Ders sayfalarının ortak iskeleti (OCW düzeni): üstte dersin mavi şeridi, solda bölümler ve
 * dersler, ortada bölüm içeriği, sağda kapatılabilir "Ders bilgisi" paneli.
 */
export default function CourseShell() {
  const { user } = useAuth();
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  const { loading, error, refresh } = useCourses();
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  if (!course) {
    if (error && !loading) {
      // Liste alınamadı: bu "ders yok" demek değildir.
      return (
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
          className="py-24"
        />
      );
    }
    return loading ? (
      <div className="page">
        <Skeleton className="h-28 w-full" />
      </div>
    ) : (
      <EmptyState
        icon={BookOpen}
        title="Ders bulunamadı"
        description="Bu ders silinmiş ya da adres hatalı olabilir. Derslerim sayfasından bir ders seç."
        className="py-24"
      />
    );
  }
  // `key`: ders değişince doküman listesi ve panel durumu sıfırlanır.
  return <CourseFrame key={course.id} course={course} role={user?.role ?? "student"} />;
}

function CourseFrame({ course, role }: { course: Course; role: "student" | "instructor" }) {
  const { pathname } = useLocation();
  const [documents, setDocuments] = useState<DocumentOut[] | null>(null);
  const [documentsFailed, setDocumentsFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [infoClosed, setInfoClosed] = useState(readInfoClosed);

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .materials(course.id, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setDocuments(list);
      })
      .catch(() => {
        if (!controller.signal.aborted) setDocumentsFailed(true);
      });
    return () => controller.abort();
  }, [course.id, attempt]);

  function reloadDocuments() {
    setDocumentsFailed(false);
    setAttempt((value) => value + 1);
  }

  function toggleInfo(closed: boolean) {
    setInfoClosed(closed);
    try {
      localStorage.setItem(INFO_KEY, closed ? "1" : "0");
    } catch {
      // tercih kaydedilemedi; sorun değil
    }
  }

  const base = coursePath(role, course.id);
  const sections: SectionLink[] =
    role === "instructor"
      ? [
          { to: base, label: "Genel bakış", icon: LayoutList, end: true },
          { to: `${base}/materials`, label: "Materyaller", icon: FolderOpen },
          { to: `${base}/activity`, label: "Etkinlik ve analitik", icon: BarChart3 },
        ]
      : [
          { to: base, label: "Genel bakış", icon: LayoutList, end: true },
          { to: `${base}/materials`, label: "Ders materyalleri", icon: FolderOpen },
          { to: `${base}/tutor`, label: "AI Tutor", icon: MessageSquareText },
        ];
  // Tutor tam yükseklikte çalışır ve sağ tarafı kaynak paneli için kullanır.
  const tutor = pathname.endsWith("/tutor");
  const outlet: CourseOutlet = { course, documents, documentsFailed, reloadDocuments };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <CourseBanner
        course={course}
        compact={tutor}
        onShowInfo={!tutor && infoClosed ? () => toggleInfo(false) : undefined}
      />
      <div className="lg:hidden">
        <SectionTabs links={sections} label="Ders bölümleri" />
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 flex-col gap-8 overflow-y-auto border-r border-line bg-surface px-3 py-6 lg:flex">
          <SectionNav links={sections} label="Ders bölümleri" />
          <OtherCourses role={role} currentId={course.id} section={currentSection(pathname, course.id)} />
        </aside>

        {tutor ? (
          <div className="min-w-0 flex-1">
            <Outlet context={outlet} />
          </div>
        ) : (
          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex max-w-[78rem] flex-col gap-8 px-5 py-8 sm:px-8 xl:flex-row xl:items-start">
              <div className="min-w-0 flex-1">
                <Outlet context={outlet} />
              </div>
              {!infoClosed && (
                <CourseInfo
                  course={course}
                  documents={documents}
                  onClose={() => toggleInfo(true)}
                  className="xl:sticky xl:top-0 xl:w-80 xl:shrink-0"
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/** Dersin mavi şeridi: "BLM2512 | Güz 2026 | Lisans" ve büyük ders adı. */
function CourseBanner({
  course,
  compact,
  onShowInfo,
}: {
  course: Course;
  compact: boolean;
  onShowInfo?: () => void;
}) {
  const meta = courseMetaParts(course);
  return (
    <div className={cx("shrink-0 bg-banner text-white", compact ? "py-3" : "py-8 lg:py-10")}>
      <div className="flex items-end justify-between gap-6 px-5 sm:px-8">
        <div className="min-w-0">
          <p className={cx("flex flex-wrap items-center font-semibold", compact ? "text-sm" : "text-base")}>
            {meta.map((part, index) => (
              <Fragment key={part}>
                {index > 0 && <span aria-hidden className="mx-2.5 h-3.5 w-px bg-white/60" />}
                {part}
              </Fragment>
            ))}
          </p>
          {compact ? (
            <p className="mt-0.5 truncate text-lg">{course.name}</p>
          ) : (
            <h1 className="mt-3 text-[2.25rem] leading-tight font-normal tracking-tight text-balance sm:text-[2.75rem]">
              {course.name}
            </h1>
          )}
        </div>
        {onShowInfo && (
          <button
            type="button"
            onClick={onShowInfo}
            className="hidden shrink-0 items-center gap-2 rounded-control border border-white/40 px-3 py-1.5 text-sm font-semibold hover:bg-white/10 sm:flex"
          >
            <Info size={16} aria-hidden />
            Ders bilgisi
          </button>
        )}
      </div>
    </div>
  );
}

/** Sol sütunun altında kullanıcının dersleri: aynı bölümde kalarak bir dersten diğerine geçiş. */
/** Adresteki bölüm ("", "/tutor", "/materials"…): ders değiştirince aynı bölümde kalınır. */
function currentSection(pathname: string, courseId: number): string {
  const marker = `/courses/${courseId}`;
  const index = pathname.indexOf(marker);
  return index === -1 ? "" : pathname.slice(index + marker.length).replace(/\/$/, "");
}

function OtherCourses({
  role,
  currentId,
  section,
}: {
  role: "student" | "instructor";
  currentId: number;
  section: string;
}) {
  const { courses } = useCourses();
  return (
    <div className="border-t border-line pt-6">
      <p className="px-3 text-sm font-bold tracking-wide text-ink uppercase">Derslerim</p>
      <ul className="mt-2 flex flex-col">
        {courses.map((item) => (
          <li key={item.id}>
            <NavLink
              to={coursePath(role, item.id) + section}
              className={cx(
                "block rounded-control px-3 py-2 text-base",
                item.id === currentId ? "font-semibold text-ink" : "text-ink-2 hover:bg-subtle hover:text-ink",
              )}
              aria-current={item.id === currentId ? "page" : undefined}
            >
              <span className="block text-xs font-semibold text-graphite">{item.code}</span>
              {item.name}
            </NavLink>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Sağ panel: yalnızca dolu bilgiler; materyal sayıları gerçek doküman listesinden. */
function CourseInfo({
  course,
  documents,
  onClose,
  className,
}: {
  course: Course;
  documents: DocumentOut[] | null;
  onClose: () => void;
  className?: string;
}) {
  const sections: InfoSection[] = [];
  if (course.instructor_name) sections.push({ label: "Eğitmen", content: course.instructor_name });
  if (course.department) sections.push({ label: "Bölüm", content: course.department });
  if (course.term) sections.push({ label: "Dönem", content: course.term });
  if (course.level) sections.push({ label: "Seviye", content: LEVEL_LABELS[course.level] });
  sections.push({ label: "Materyal dili", content: languageLabel(course.language) });

  if (documents === null) {
    sections.push({ label: "Ders materyali", content: <Skeleton className="h-4 w-32" /> });
  } else if (documents.length > 0) {
    const byType = new Map<string, number>();
    for (const document of documents) {
      byType.set(document.material_type, (byType.get(document.material_type) ?? 0) + 1);
    }
    const latest = documents.reduce((a, b) => (a.created_at > b.created_at ? a : b));
    const totals = materialTotals(documents);
    sections.push({
      label: "Ders materyali",
      content: (
        <ul className="flex flex-col gap-1">
          {[...byType].map(([type, count]) => (
            <li key={type} className="flex justify-between gap-4">
              <span>{MATERIAL_LABELS[type as keyof typeof MATERIAL_LABELS] ?? type}</span>
              <span className="font-semibold text-ink tabular-nums">{count}</span>
            </li>
          ))}
          {totals.hasPages && (
            <li className="mt-1 flex justify-between gap-4 border-t border-line pt-1">
              <span>Toplam sayfa</span>
              <span className="font-semibold text-ink tabular-nums">{totals.pages}</span>
            </li>
          )}
          {totals.hasVideo && (
            <li
              className={`flex justify-between gap-4 ${totals.hasPages ? "" : "mt-1 border-t border-line pt-1"}`}
            >
              <span>Video süresi</span>
              <span className="font-semibold text-ink tabular-nums">{formatTime(totals.videoSeconds)}</span>
            </li>
          )}
        </ul>
      ),
    });
    sections.push({ label: "Son güncelleme", content: formatRelative(latest.created_at) });
  }

  return (
    <div className={className}>
      <InfoPanel title="Ders bilgisi" sections={sections} onClose={onClose} />
      <p className="mt-3 px-1 text-sm text-graphite">
        <Link to="/" className="link">
          Tüm derslerim
        </Link>
      </p>
    </div>
  );
}
