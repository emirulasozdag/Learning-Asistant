import { useState } from "react";
import { Outlet } from "react-router";

import CoursesProvider from "../features/courses/CoursesProvider";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

const COLLAPSE_KEY = "la.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Giriş sonrası iskelet: daraltılabilir sidebar + topbar + içerik. */
export default function AppShell() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [mobileOpen, setMobileOpen] = useState(false);

  function toggle() {
    setCollapsed((value) => {
      try {
        localStorage.setItem(COLLAPSE_KEY, value ? "0" : "1");
      } catch {
        // tercih kaydedilemedi; sorun değil
      }
      return !value;
    });
  }

  return (
    <CoursesProvider>
      <div className="flex h-dvh overflow-hidden">
        <div className="hidden lg:block">
          <Sidebar collapsed={collapsed} onToggle={toggle} />
        </div>

        {mobileOpen && (
          <div className="fixed inset-0 z-40 lg:hidden">
            <div
              className="fade-in absolute inset-0 bg-ink/25"
              onClick={() => setMobileOpen(false)}
              aria-hidden
            />
            <div className="fade-in relative h-full w-60">
              <Sidebar
                collapsed={false}
                onToggle={() => setMobileOpen(false)}
                onNavigate={() => setMobileOpen(false)}
              />
            </div>
          </div>
        )}

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onOpenMenu={() => setMobileOpen(true)} />
          <main className="min-h-0 flex-1 overflow-y-auto">
            <Outlet />
          </main>
        </div>
      </div>
    </CoursesProvider>
  );
}
