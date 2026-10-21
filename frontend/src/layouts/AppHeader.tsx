import { LogOut, Menu } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import Avatar from "../ui/Avatar";
import { cx } from "../ui/cx";
import IconButton from "../ui/IconButton";
import Logo from "../ui/Logo";
import UniversityLogo from "../ui/UniversityLogo";
import { NAVIGATION, ROLE_LABELS } from "./navigation";

/** Üst bar: kurum ve ürün işareti, ana gezinme ve kullanıcı (çalışma alanıyla aynı açık görünüm). */
export default function AppHeader({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  if (!user) return null;
  // Ders içindeyken: tutor bölümünde "AI Tutor", diğer bölümlerde "Derslerim" seçili görünür.
  const inTutor = pathname.endsWith("/tutor");

  return (
    <header className="flex h-[4.5rem] shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-3 backdrop-blur sm:px-8">
      <IconButton icon={Menu} label="Menüyü aç" onClick={onOpenMenu} className="md:hidden" />
      <UniversityLogo className="hidden sm:inline-flex" />
      <Link to={homePath(user.role)} className="mr-4 rounded-control px-1 py-1 lg:mr-8" aria-label="Ana sayfa">
        <Logo />
      </Link>

      <nav aria-label="Ana gezinme" className="ml-auto hidden h-full items-stretch gap-2 md:flex">
        {NAVIGATION[user.role].map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={() => {
              const isActive = to.endsWith("/tutor") ? inTutor : !inTutor;
              return cx(
                "my-auto flex h-9 items-center rounded-control px-3 text-sm font-semibold transition-colors",
                isActive ? "bg-accent-soft text-accent" : "text-ink-2 hover:bg-subtle hover:text-ink",
              );
            }}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-3 md:ml-6 md:border-l md:border-line md:pl-6">
        <div className="hidden text-right sm:block">
          <p className="text-sm leading-tight font-semibold text-ink">{user.name}</p>
          <p className="text-xs text-graphite">{ROLE_LABELS[user.role]}</p>
        </div>
        <Avatar name={user.name} className="bg-accent text-on-accent" />
        <IconButton icon={LogOut} label="Çıkış yap" onClick={() => void logout()} />
      </div>
    </header>
  );
}
