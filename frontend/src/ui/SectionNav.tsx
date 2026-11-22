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

/** Dersin bölümleri: dikey liste; seçili bölüm lacivert zemin ve soldaki çizgiyle belirgin. */
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
                  "relative flex items-center gap-3 rounded-control px-3 py-2.5 text-md transition-colors",
                  isActive
                    ? "bg-accent-soft font-semibold text-accent before:absolute before:inset-y-2 before:left-0 before:w-0.75 before:rounded-full before:bg-accent"
                    : "text-ink-2 hover:bg-subtle hover:text-ink",
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
    <nav aria-label={label} className="flex gap-6 overflow-x-auto border-b border-line bg-surface px-5 sm:px-8">
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
