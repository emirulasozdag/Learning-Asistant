import { NavLink } from "react-router";

import { cx } from "./cx";

export interface TabLink {
  to: string;
  label: string;
  /** Henüz geliştirilmekte olan bölüm: sekme görünür, küçük bir işaret taşır. */
  upcoming?: boolean;
}

const tabClass = (active: boolean) =>
  cx(
    "-mb-px flex h-10 items-center gap-1.5 border-b-2 text-base transition-colors",
    active
      ? "border-ink font-medium text-ink"
      : "border-transparent text-graphite hover:border-line-strong hover:text-ink",
  );

/** Adres çubuğuna bağlı sekmeler (ör. ders sayfası). */
export function RouteTabs({ tabs, label }: { tabs: TabLink[]; label: string }) {
  return (
    <nav aria-label={label} className="flex gap-6 overflow-x-auto border-b border-line">
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} end className={({ isActive }) => tabClass(isActive)}>
          {tab.label}
          {tab.upcoming && (
            <span aria-label="geliştiriliyor" className="size-1.5 rounded-full bg-line-strong" />
          )}
        </NavLink>
      ))}
    </nav>
  );
}
