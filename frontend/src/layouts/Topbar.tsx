import { ChevronRight, Menu } from "lucide-react";
import { Fragment } from "react";
import { Link, useLocation, useParams } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourse } from "../features/courses/context";
import IconButton from "../ui/IconButton";

interface Crumb {
  label: string;
  to?: string;
}

const SECTION_LABELS: Record<string, string> = {
  overview: "Genel bakış",
  materials: "Materyaller",
  students: "Öğrenciler",
  analytics: "Analitik",
  tutor: "AI Tutor",
  practice: "Pratik",
};

/** Adresten ekmek kırıntısı: Genel bakış / BLM2512 / Materyaller. */
function useBreadcrumbs(): Crumb[] {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const params = useParams();
  const course = useCourse(params.courseId ? Number(params.courseId) : null);
  if (!user) return [];

  const home: Crumb =
    user.role === "instructor"
      ? { label: "Genel bakış", to: "/instructor" }
      : { label: "Ana sayfa", to: "/student" };
  const crumbs: Crumb[] = [home];
  const last = pathname.split("/").filter(Boolean).pop() ?? "";

  if (params.courseId) {
    const base =
      user.role === "instructor"
        ? `/instructor/courses/${params.courseId}`
        : `/student/courses/${params.courseId}/tutor`;
    crumbs.push({ label: course ? course.code : "Ders", to: base });
  }
  if (SECTION_LABELS[last] && !(user.role === "instructor" && last === "overview")) {
    crumbs.push({ label: SECTION_LABELS[last] });
  }
  if (crumbs.length > 1) delete crumbs[crumbs.length - 1].to;
  return crumbs;
}

export default function Topbar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const crumbs = useBreadcrumbs();
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-line bg-surface/80 px-4 backdrop-blur lg:px-6">
      <IconButton icon={Menu} label="Menüyü aç" onClick={onOpenMenu} className="lg:hidden" />
      <nav aria-label="Konum" className="min-w-0">
        <ol className="flex items-center gap-1.5 text-base">
          {crumbs.map((crumb, index) => (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && <ChevronRight size={14} aria-hidden className="shrink-0 text-faint" />}
              <li className="min-w-0 truncate">
                {crumb.to ? (
                  <Link to={crumb.to} className="text-graphite hover:text-ink">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="font-medium text-ink">
                    {crumb.label}
                  </span>
                )}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>
    </header>
  );
}
