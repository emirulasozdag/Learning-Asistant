import { BookOpen, ServerOff } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Outlet, useParams } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourse, useCourses } from "../features/courses/context";
import CommandPalette from "../features/studio/CommandPalette";
import { StudioContext, type ConversationEntry, type StudioContextValue } from "../features/studio/context";
import StudioSidebar from "../features/studio/StudioSidebar";
import StudioTopbar from "../features/studio/StudioTopbar";
import { topicOf } from "../features/studio/topic";
import Button from "../ui/Button";
import EmptyState from "../ui/EmptyState";
import { SkeletonRows } from "../ui/Skeleton";
import { coursePath } from "./navigation";

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * AI Tutor çalışma alanı: solda kurum, ders ve araçlar; üstte konum ve arama; ortada sayfa.
 * Uygulamanın üst barı burada yoktur, ekranın tamamı soru, cevap ve kaynağa ayrılır.
 */
export default function StudioShell() {
  const courseId = Number(useParams().courseId);
  const course = useCourse(courseId);
  const { courses, loading, error, refresh } = useCourses();
  const { user } = useAuth();
  const [retrying, setRetrying] = useState(false);

  const [entries, setEntries] = useState<ConversationEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [queuedQuestion, setQueuedQuestion] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const selectHandler = useRef<((id: string) => void) | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // Dar ekran menüsü: odak içeri taşınır ve içeride kalır; kapanınca açan düğmeye döner.
  useEffect(() => {
    if (!menuOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = menuRef.current;
    const focusable = () =>
      [...(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].filter(
        (element) => !element.hasAttribute("disabled") && element.tabIndex !== -1,
      );
    (focusable()[0] ?? panel)?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (!panel?.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [menuOpen]);

  const publish = useCallback((list: ConversationEntry[], active: string | null) => {
    setEntries(list);
    setActiveId(active);
  }, []);

  const studio = useMemo<StudioContextValue>(
    () => ({
      entries,
      activeId,
      publish,
      select: (id) => selectHandler.current?.(id),
      onSelect: (handler) => {
        selectHandler.current = handler;
      },
      queuedQuestion,
      queueQuestion: setQueuedQuestion,
    }),
    [entries, activeId, publish, queuedQuestion],
  );

  async function retry() {
    setRetrying(true);
    await refresh();
    setRetrying(false);
  }

  if (!course) {
    if (loading) {
      return (
        <div className="mx-auto max-w-3xl px-6 pt-16">
          <SkeletonRows rows={3} />
        </div>
      );
    }
    if (error) {
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
    return (
      <EmptyState
        icon={BookOpen}
        title="Ders bulunamadı"
        description="Bu ders silinmiş ya da adres hatalı olabilir. Derslerim sayfasından bir ders seç."
        className="py-24"
      />
    );
  }

  const active = entries.find((entry) => entry.id === activeId) ?? null;
  const base = coursePath(user?.role ?? "student", course.id);

  return (
    <StudioContext.Provider value={studio}>
      <div className="studio-grid flex h-dvh overflow-hidden">
        <aside className="hidden w-72 shrink-0 border-r border-line lg:block">
          <StudioSidebar course={course} courses={courses} />
        </aside>

        {menuOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div className="fade-in absolute inset-0 bg-ink/30" onClick={() => setMenuOpen(false)} aria-hidden />
            <div
              ref={menuRef}
              role="dialog"
              aria-modal="true"
              aria-label="Menü"
              tabIndex={-1}
              className="slide-in-left relative h-full w-80 max-w-[85vw] bg-canvas shadow-float"
            >
              <StudioSidebar course={course} courses={courses} onNavigate={() => setMenuOpen(false)} />
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col" inert={menuOpen}>
          <StudioTopbar
            course={course}
            topic={topicOf(active?.question ?? null)}
            onOpenSearch={() => setPaletteOpen(true)}
            onOpenMenu={() => setMenuOpen(true)}
          />
          <main className="min-h-0 flex-1">
            <Outlet />
          </main>
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        courseId={course.id}
        base={base}
        onAsk={(question) => setQueuedQuestion(question)}
      />
    </StudioContext.Provider>
  );
}
