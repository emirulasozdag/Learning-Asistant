import { useState } from "react";
import { Outlet } from "react-router";

import CoursesProvider from "../features/courses/CoursesProvider";
import AppHeader from "./AppHeader";
import MobileMenu from "./MobileMenu";
import Topbar from "./Topbar";

/** Giriş sonrası iskelet: kurumsal üst bar, konum şeridi ve içerik. */
export default function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <CoursesProvider>
      <div className="flex h-dvh flex-col overflow-hidden">
        <AppHeader onOpenMenu={() => setMobileOpen(true)} />

        <div className="flex min-h-0 flex-1">
          {mobileOpen && (
            <div className="fixed inset-0 z-40 md:hidden">
              <div
                className="fade-in absolute inset-0 bg-ink/30"
                onClick={() => setMobileOpen(false)}
                aria-hidden
              />
              <div className="slide-in-left relative h-full w-72 shadow-float">
                <MobileMenu onNavigate={() => setMobileOpen(false)} />
              </div>
            </div>
          )}

          <div className="flex min-w-0 flex-1 flex-col">
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
