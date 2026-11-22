import { BookOpen, Info, Search, ServerOff } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useParams } from "react-router";

import type { CourseOutline, DocumentOut } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { useCourse, useCourses } from "../features/courses/context";
import type { CourseOutlet } from "../features/courses/courseOutlet";
import ConversationList from "../features/studio/ConversationList";
import StudioProvider from "../features/studio/StudioProvider";
import { useStudio } from "../features/studio/useStudio";
import { contentSections, toolSections } from "../features/courses/sections";
import { Breadcrumbs } from "./Topbar";
import { LEVEL_LABELS, MATERIAL_LABELS, courseMetaParts, languageLabel, materialTotals } from "../labels";
import { courseService, type Course } from "../services/courseService";
import { formatRelative, formatTime } from "../text";
import Button from "../ui/Button";
import { buttonClasses } from "../ui/buttonStyles";
import { cx } from "../ui/cx";
import EmptyState from "../ui/EmptyState";
import InfoPanel, { type InfoSection } from "../ui/InfoPanel";
import { SectionNav, SectionTabs } from "../ui/SectionNav";
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
        action={
          <Link to="/" className={buttonClasses("primary")}>
            Derslerime dön
          </Link>
        }
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
  const [outline, setOutline] = useState<CourseOutline | null>(null);
  const [outlineFailed, setOutlineFailed] = useState(false);
  const [outlineAttempt, setOutlineAttempt] = useState(0);

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

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .outline(course.id, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setOutline(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setOutlineFailed(true);
      });
    return () => controller.abort();
  }, [course.id, outlineAttempt]);

  function reloadOutline() {
    setOutlineFailed(false);
    setOutline(null);
    setOutlineAttempt((value) => value + 1);
  }

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
  const tools = toolSections(role, base);
  const content = contentSections(role, base);
  // Tutor tam yükseklikte çalışır ve sağ tarafı kaynak paneli için kullanır.
  const tutor = pathname.endsWith("/tutor");
  const outlet: CourseOutlet = {
    course,
    documents,
    documentsFailed,
    reloadDocuments,
    outline,
    outlineFailed,
    reloadOutline,
  };

  const frame = (
    <div className="flex h-full min-h-0 flex-col">
      <CourseBanner
        course={course}
        searchable={role === "student"}
        onShowInfo={!tutor && infoClosed ? () => toggleInfo(false) : undefined}
      />
      <div className="lg:hidden">
        <SectionTabs links={[...tools, ...content]} label="Ders bölümleri" />
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 flex-col gap-8 overflow-y-auto border-r border-line bg-surface px-3 py-6 lg:flex">
          <SectionNav links={tools} label="Ders araçları" />
          {tutor && <TutorConversation />}
          <div className="border-t border-line pt-6">
            <p className="px-3 text-sm font-semibold text-graphite">Ders içeriği</p>
            <div className="mt-2">
              <SectionNav links={content} label="Ders içeriği" />
            </div>
          </div>
          <OtherCourses role={role} currentId={course.id} section={currentSection(pathname, course.id)} />
        </aside>

        {tutor ? (
          <div className="min-w-0 flex-1">
            <Outlet context={outlet} />
          </div>
        ) : (
          <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
            {/* Ders bilgisi paneli çok geniş ekranda (2xl) yanda durur; daha darda içeriğin altına
                iner, böylece takvim ve materyal tabloları daralmaz (#106). */}
            <div className="page flex flex-col gap-8 2xl:flex-row 2xl:items-start">
              <div className="min-w-0 flex-1">
                <Outlet context={outlet} />
              </div>
              {!infoClosed && (
                <CourseInfo
                  course={course}
                  documents={documents}
                  onClose={() => toggleInfo(true)}
                  className="2xl:sticky 2xl:top-0 2xl:w-72 2xl:shrink-0"
                />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
  return role === "student" ? (
    <StudioProvider courseId={course.id} base={base} tutorPath={`${base}/tutor`}>
      {frame}
    </StudioProvider>
  ) : (
    frame
  );
}

/** AI Tutor açıkken sol menüde "Bu sohbet": sorulan sorular, birine dokununca o soru açılır. */
function TutorConversation() {
  const { entries, activeId, select } = useStudio();
  return (
    <div className="border-t border-line px-1 pt-6">
      <ConversationList entries={entries} activeId={activeId} onSelect={select} />
    </div>
  );
}

/**
 * Dersin şeridi: konum ("Derslerim / 18.06 / Takvim"), ders adı ve ders bilgileri. Bütün ders
 * sayfalarında (AI Tutor dahil) aynı boyuttadır; bölümler arasında geçerken üst kısım kaymaz.
 */
function CourseBanner({
  course,
  searchable,
  onShowInfo,
}: {
  course: Course;
  /** Öğrenci: materyal araması (Ctrl/⌘+K) düğmesi. */
  searchable: boolean;
  onShowInfo?: () => void;
}) {
  const [, ...details] = courseMetaParts(course);
  return (
    <div className="shrink-0 border-b border-line bg-surface px-5 pt-3 pb-4 text-ink sm:px-8">
      <Breadcrumbs />
      <div className="mt-2 flex items-end justify-between gap-6">
        <div className="min-w-0">
          {/* Sayfanın başlığı (h1) bölüm başlığıdır (Takvim, Ders notları…); ders adı şerittir (#106). */}
          <p className="truncate text-2xl font-bold tracking-tight text-ink">{course.name}</p>
          <p className="mt-1.5 flex flex-wrap items-center gap-2 text-sm text-graphite">
            <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-xs font-semibold text-accent tabular-nums">
              {course.code}
            </span>
            {details.map((part, index) => (
              <Fragment key={part}>
                {index > 0 && <span aria-hidden className="h-3.5 w-px bg-line-strong" />}
                <span>{part}</span>
              </Fragment>
            ))}
          </p>
        </div>
        {/* Dar ekranda arama ve bilgi düğmeleri gizlenir (menüde ve sekmelerde ulaşılır). */}
        <div className="hidden shrink-0 items-center gap-2 sm:flex">
          {searchable && <SearchButton />}
          {onShowInfo && (
            <Button size="sm" icon={Info} onClick={onShowInfo}>
              Ders bilgisi
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** Adresteki bölüm ("", "/tutor", "/materials"…): ders değiştirince aynı bölümde kalınır. */
function currentSection(pathname: string, courseId: number): string {
  const marker = `/courses/${courseId}`;
  const index = pathname.indexOf(marker);
  return index === -1 ? "" : pathname.slice(index + marker.length).replace(/\/$/, "");
}

/** Sol sütunun altında kullanıcının dersleri: aynı bölümde kalarak bir dersten diğerine geçiş. */
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
      <p className="px-3 text-sm font-semibold text-graphite">Derslerim</p>
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

function SearchButton() {
  const { openSearch } = useStudio();
  return (
    <Button size="sm" icon={Search} onClick={openSearch}>
      Materyalde ara
      <kbd className="rounded border border-line px-1 font-mono text-xs font-normal text-graphite">Ctrl K</kbd>
    </Button>
  );
}
