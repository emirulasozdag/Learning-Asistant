import { Check, ChevronDown, LayoutGrid } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import type { Course } from "../../services/courseService";
import { cx } from "../../ui/cx";

/**
 * Kenar çubuğundaki ders seçici: açılınca kullanıcının dersleri listelenir; başka bir derse
 * geçince aynı araçta (ör. AI Tutor) kalınır. Dışarı tıklama ve Escape kapatır.
 */
export default function CourseSwitcher({
  course,
  courses,
  pathFor,
  allCoursesPath,
}: {
  course: Course;
  courses: Course[];
  /** Seçilen dersin aynı araçtaki adresi. */
  pathFor: (course: Course) => string;
  allCoursesPath: string;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointer(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <p className="mb-1.5 px-1 text-xs font-medium text-graphite">Ders</p>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 rounded-panel border border-line bg-surface px-3 py-2.5 text-left shadow-card transition-colors hover:border-line-strong"
      >
        <span className="min-w-0 flex-1">
          <span className="block font-mono text-xs font-medium text-accent">{course.code}</span>
          <span className="block text-sm leading-snug font-semibold text-ink">{course.name}</span>
        </span>
        <ChevronDown
          size={15}
          aria-hidden
          className={cx("shrink-0 text-graphite transition-transform", open && "rotate-180")}
        />
      </button>

      {open && (
        <div
          id={menuId}
          className="fade-in absolute inset-x-0 top-full z-30 mt-1.5 overflow-hidden rounded-panel border border-line bg-surface shadow-float"
        >
          <ul className="max-h-72 overflow-y-auto py-1">
            {courses.map((item) => {
              const current = item.id === course.id;
              return (
                <li key={item.id}>
                  <Link
                    to={pathFor(item)}
                    onClick={() => setOpen(false)}
                    aria-current={current ? "page" : undefined}
                    className={cx(
                      "flex items-start gap-2 px-3 py-2 text-sm",
                      current ? "bg-accent-soft" : "hover:bg-subtle",
                    )}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-xs text-graphite">{item.code}</span>
                      <span className="block text-ink">{item.name}</span>
                    </span>
                    {current && <Check size={14} aria-hidden className="mt-1 shrink-0 text-accent" />}
                  </Link>
                </li>
              );
            })}
          </ul>
          <Link
            to={allCoursesPath}
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 border-t border-line px-3 py-2.5 text-sm text-ink-2 hover:bg-subtle"
          >
            <LayoutGrid size={14} aria-hidden />
            Tüm derslerim
          </Link>
        </div>
      )}
    </div>
  );
}
