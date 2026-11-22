import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { Link, useLocation, useParams } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourse } from "../features/courses/context";
import { SECTION_LABELS } from "../features/courses/sections";
import { cx } from "../ui/cx";

interface Crumb {
  label: string;
  to?: string;
}

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
  // Öğrencinin materyal sayfası bütün türleri gösterir; başlığıyla aynı adı taşır.
  const label = last === "materials" && user.role === "student" ? "Tüm materyaller" : SECTION_LABELS[last];
  if (label) crumbs.push({ label });
  // Video izleme ekranı konumu kendisi sürdürür ("Ders videoları › video adı"); ders kodu bağlantı kalır.
  if (crumbs.length > 1 && !pathname.includes("/watch/")) delete crumbs[crumbs.length - 1].to;
  return crumbs;
}

/** Konum: "Derslerim / 18.06 / Takvim". Ders sayfalarında ders şeridinin içinde durur. */
export function Breadcrumbs({ className }: { className?: string }) {
  const crumbs = useBreadcrumbs();
  if (crumbs.length < 2) return null;
  return (
    <nav aria-label="Konum" className={cx("min-w-0", className)}>
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
  );
}

/**
 * Konum şeridi: ders dışı alt sayfalarda (ör. Hesabım) üst çubuğun altında. Ders sayfaları ve
 * video ekranı konumu kendi şeritlerinde gösterir; orada ayrı satır yoktur.
 */
export default function Topbar() {
  const params = useParams();
  const crumbs = useBreadcrumbs();
  if (params.courseId || crumbs.length < 2) return null;
  return (
    <div className="flex h-11 shrink-0 items-center border-b border-line bg-surface px-5 sm:px-8">
      <Breadcrumbs />
    </div>
  );
}
