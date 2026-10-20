import { Menu, Search } from "lucide-react";
import { Fragment } from "react";

import type { Course } from "../../services/courseService";
import { cx } from "../../ui/cx";

/** Kısa yol tuşunun platforma göre adı. */
function shortcutLabel(): string {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘ K" : "Ctrl K";
}

/** Üst şerit: konum yolu ve materyal araması (Ctrl K). Dar ekranda menü düğmesi de burada. */
export default function StudioTopbar({
  course,
  topic,
  onOpenSearch,
  onOpenMenu,
}: {
  course: Course;
  topic: string | null;
  onOpenSearch: () => void;
  onOpenMenu: () => void;
}) {
  const trail = [course.code, "AI Tutor", topic].filter((part): part is string => Boolean(part));
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 px-4 sm:px-6">
      <button
        type="button"
        onClick={onOpenMenu}
        aria-label="Menüyü aç"
        className="flex size-9 items-center justify-center rounded-control text-ink-2 hover:bg-subtle lg:hidden"
      >
        <Menu size={18} aria-hidden />
      </button>

      <nav aria-label="Konum" className="min-w-0 flex-1">
        <ol className="flex min-w-0 items-center gap-2 font-mono text-xs text-graphite">
          {trail.map((part, index) => (
            <Fragment key={`${index}-${part}`}>
              {index > 0 && (
                <li aria-hidden className="text-faint">
                  /
                </li>
              )}
              <li
                className={cx(
                  "truncate",
                  index === trail.length - 1 ? "font-semibold text-ink" : "shrink-0",
                )}
                aria-current={index === trail.length - 1 ? "page" : undefined}
              >
                {part}
              </li>
            </Fragment>
          ))}
        </ol>
      </nav>

      <button
        type="button"
        onClick={onOpenSearch}
        className="hidden h-9 w-72 items-center gap-2 rounded-control border border-line bg-surface px-3 text-sm text-faint shadow-card transition-colors hover:border-line-strong hover:text-graphite md:flex"
      >
        <Search size={15} aria-hidden />
        <span className="flex-1 truncate text-left">Materyalde ara: {topic ?? course.name}</span>
        <kbd className="rounded-[3px] border border-line px-1.5 font-mono text-[11px] text-graphite">
          {shortcutLabel()}
        </kbd>
      </button>
      <button
        type="button"
        onClick={onOpenSearch}
        aria-label="Materyalde ara"
        className="flex size-9 items-center justify-center rounded-control text-ink-2 hover:bg-subtle md:hidden"
      >
        <Search size={17} aria-hidden />
      </button>
    </header>
  );
}
