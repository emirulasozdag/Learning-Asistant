import { LogOut, Menu } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import Avatar from "../ui/Avatar";
import { cx } from "../ui/cx";
import IconButton from "../ui/IconButton";
import Logo from "../ui/Logo";
import { NAVIGATION, ROLE_LABELS } from "./navigation";

/** Kurumsal üst bar: sözcük işareti, ana gezinme ve kullanıcı. */
export default function AppHeader({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  if (!user) return null;
  // Ders içindeyken: tutor bölümünde "AI Tutor", diğer bölümlerde "Derslerim" seçili görünür.
  const inTutor = pathname.endsWith("/tutor");

  return (
    <header className="flex h-[4.5rem] shrink-0 items-center gap-2 bg-nav px-3 text-white sm:px-8">
      <IconButton icon={Menu} label="Menüyü aç" onClick={onOpenMenu} tone="dark" className="md:hidden" />
      <Link to={homePath(user.role)} className="mr-4 rounded-control px-1 py-1 lg:mr-8" aria-label="Ana sayfa">
        <Logo onDark />
      </Link>

      <nav aria-label="Ana gezinme" className="ml-auto hidden h-full items-stretch gap-2 md:flex">
        {NAVIGATION[user.role].map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={() => {
              const isActive = to.endsWith("/tutor") ? inTutor : !inTutor;
              return cx(
                "relative flex items-center px-3 text-sm font-bold tracking-wide uppercase transition-colors",
                "after:absolute after:inset-x-3 after:bottom-0 after:h-[3px] after:rounded-t-sm",
                isActive ? "text-white after:bg-accent" : "text-white/80 hover:text-white after:bg-transparent",
              );
            }}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3 md:ml-6 md:border-l md:border-nav-line md:pl-6">
        <div className="hidden text-right sm:block">
          <p className="text-sm leading-tight font-semibold text-white">{user.name}</p>
          <p className="text-xs text-nav-muted">{ROLE_LABELS[user.role]}</p>
        </div>
        <Avatar name={user.name} className="bg-accent" />
        <IconButton icon={LogOut} label="Çıkış yap" onClick={() => void logout()} tone="dark" />
      </div>
    </header>
  );
}
