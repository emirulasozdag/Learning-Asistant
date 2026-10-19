import type { LucideIcon } from "lucide-react";
import { NavLink } from "react-router";

import { cx } from "./cx";

export interface SectionLink {
  to: string;
  label: string;
  icon?: LucideIcon;
  /** Alt adreslerde etkin sayılmasın (ör. genel bakış). */
  end?: boolean;
}

/** Dersin bölümleri: dikey liste; seçili bölüm bordo ve kalın (OCW sol menüsü gibi). */
export function SectionNav({ links, label }: { links: SectionLink[]; label: string }) {
  return (
    <nav aria-label={label}>
      <ul className="flex flex-col">
        {links.map(({ to, label: text, icon: Icon, end }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                cx(
                  "flex items-center gap-3 rounded-control px-3 py-2.5 text-md transition-colors",
                  isActive ? "font-semibold text-accent" : "text-ink hover:bg-subtle",
                )
              }
            >
              {Icon && <Icon size={18} aria-hidden className="shrink-0 opacity-80" />}
              {text}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** Dar ekranda aynı bölümler: yatay, kaydırılabilir sekme satırı. */
export function SectionTabs({ links, label }: { links: SectionLink[]; label: string }) {
  return (
    <nav aria-label={label} className="flex gap-6 overflow-x-auto border-b border-line bg-surface px-5">
      {links.map(({ to, label: text, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cx(
              "-mb-px flex h-12 shrink-0 items-center border-b-[3px] text-base transition-colors",
              isActive
                ? "border-accent font-semibold text-accent"
                : "border-transparent font-medium text-ink-2 hover:text-ink",
            )
          }
        >
          {text}
        </NavLink>
      ))}
    </nav>
  );
}
