import { NavLink } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourses } from "../features/courses/context";
import { cx } from "../ui/cx";
import Logo from "../ui/Logo";
import { NAVIGATION, coursePath } from "./navigation";

const itemClass = ({ isActive }: { isActive: boolean }) =>
  cx(
    "block rounded-control px-3 py-2.5 text-md",
    isActive ? "font-semibold text-accent" : "text-ink hover:bg-subtle",
  );

/** Dar ekran menüsü: ana gezinme ve dersler (geniş ekranda üst bar ve ders sayfasının solu). */
export default function MobileMenu({ onNavigate }: { onNavigate: () => void }) {
  const { user } = useAuth();
  const { courses } = useCourses();
  if (!user) return null;
  return (
    <aside aria-label="Menü" className="flex h-full flex-col overflow-y-auto bg-surface">
      <div className="flex h-[4.5rem] shrink-0 items-center border-b border-line bg-surface px-5">
        <Logo onDark />
      </div>
      <nav className="flex flex-col gap-6 px-3 py-5">
        <ul>
          {NAVIGATION[user.role].map(({ to, label, end }) => (
            <li key={to}>
              <NavLink to={to} end={end} onClick={onNavigate} className={itemClass}>
                {label}
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="border-t border-line pt-5">
          <p className="px-3 text-sm font-bold tracking-wide text-ink uppercase">Derslerim</p>
          <ul className="mt-2">
            {courses.map((course) => (
              <li key={course.id}>
                <NavLink to={coursePath(user.role, course.id)} onClick={onNavigate} className={itemClass}>
                  <span className="block text-xs font-semibold text-graphite">{course.code}</span>
                  {course.name}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      </nav>
    </aside>
  );
}
