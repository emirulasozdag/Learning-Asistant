import { NavLink } from "react-router";

import { cx } from "../../ui/cx";
import { studioLinks } from "./studioLinks";

export default function StudioNav({ base, onNavigate }: { base: string; onNavigate?: () => void }) {
  return (
    <nav aria-label="Ders araçları">
      <ul className="flex flex-col gap-0.5">
        {studioLinks(base).map(({ label, icon: Icon, to, end }) => (
          <li key={label}>
            {to ? (
              <NavLink
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cx(
                    "flex min-h-10 items-center gap-3 rounded-control px-3 text-sm transition-colors",
                    isActive
                      ? "bg-accent-soft font-semibold text-accent"
                      : "text-ink-2 hover:bg-subtle hover:text-ink",
                  )
                }
              >
                <Icon size={16} aria-hidden />
                {label}
              </NavLink>
            ) : (
              <span
                aria-disabled="true"
                className="flex min-h-10 items-center gap-3 rounded-control px-3 text-sm text-faint"
              >
                <Icon size={16} aria-hidden />
                {label}
                <span className="ml-auto rounded-full border border-line px-1.5 text-[10px] leading-4 font-medium">
                  yakında
                </span>
              </span>
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
