import { useEffect, useRef, useState } from "react";
import { Outlet } from "react-router";

import CoursesProvider from "../features/courses/CoursesProvider";
import AppHeader from "./AppHeader";
import MobileMenu from "./MobileMenu";
import Topbar from "./Topbar";

const FOCUSABLE = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * Giriş sonrası tek iskelet (#103): kurumsal üst bar, konum şeridi ve içerik. AI Tutor dahil bütün
 * sayfalar bunun içinde açılır.
 */
export default function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Dar ekran menüsü: odak içeri taşınır ve içeride kalır, Escape kapatır; kapanınca açan
  // düğmeye döner (#106).
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = menuRef.current;
    const focusable = () =>
      [...(panel?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? [])].filter(
        (element) => !element.hasAttribute("disabled") && element.tabIndex !== -1,
      );
    (focusable()[0] ?? panel)?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
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
  }, [mobileOpen]);

  return (
    <CoursesProvider>
      <div className="studio-grid flex h-dvh flex-col overflow-hidden">
        <AppHeader onOpenMenu={() => setMobileOpen(true)} />

        <div className="flex min-h-0 flex-1">
          {mobileOpen && (
            <div className="fixed inset-0 z-40 md:hidden">
              <div
                className="fade-in absolute inset-0 bg-scrim"
                onClick={() => setMobileOpen(false)}
                aria-hidden
              />
              <div
                ref={menuRef}
                role="dialog"
                aria-modal="true"
                aria-label="Menü"
                tabIndex={-1}
                className="slide-in-left relative h-full w-72 shadow-float"
              >
                <MobileMenu onNavigate={() => setMobileOpen(false)} />
              </div>
            </div>
          )}

          <div className="flex min-w-0 flex-1 flex-col" inert={mobileOpen}>
            <Topbar />
            <main className="min-h-0 flex-1 overflow-y-auto">
              <Outlet />
            </main>
          </div>
        </div>
      </div>
    </CoursesProvider>
  );
}
