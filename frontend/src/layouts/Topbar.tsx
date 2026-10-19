import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { Link, useLocation, useParams } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourse } from "../features/courses/context";

interface Crumb {
  label: string;
  to?: string;
}

const SECTION_LABELS: Record<string, string> = {
  materials: "Materyaller",
  activity: "Etkinlik ve analitik",
  tutor: "AI Tutor",
};

/** Adresten ekmek kırıntısı: Derslerim / BLM2512 / Materyaller. */
function useBreadcrumbs(): Crumb[] {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const params = useParams();
  const course = useCourse(params.courseId ? Number(params.courseId) : null);
  if (!user) return [];

  const home: Crumb = { label: "Derslerim", to: user.role === "instructor" ? "/instructor" : "/student" };
  const crumbs: Crumb[] = [home];
  const last = pathname.split("/").filter(Boolean).pop() ?? "";

  if (params.courseId) {
    const base = `/${user.role}/courses/${params.courseId}`;
    crumbs.push({ label: course ? course.code : "Ders", to: base });
  }
  if (SECTION_LABELS[last]) {
    crumbs.push({ label: SECTION_LABELS[last] });
  }
  if (crumbs.length > 1) delete crumbs[crumbs.length - 1].to;
  return crumbs;
}

/** Konum şeridi: yalnızca ana sayfanın altındaki sayfalarda görünür. */
export default function Topbar() {
  const crumbs = useBreadcrumbs();
  if (crumbs.length < 2) return null;
  return (
    <div className="flex h-11 shrink-0 items-center border-b border-line bg-surface px-4 lg:px-6">
      <nav aria-label="Konum" className="min-w-0">
        <ol className="flex items-center gap-1.5 text-sm">
          {crumbs.map((crumb, index) => (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 && <ChevronRight size={14} aria-hidden className="shrink-0 text-faint" />}
              <li className="min-w-0 truncate">
                {crumb.to ? (
                  <Link to={crumb.to} className="text-graphite hover:text-accent hover:underline">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current="page" className="font-semibold text-ink">
                    {crumb.label}
                  </span>
                )}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>
    </div>
  );
}
