import { LogOut, Menu } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import Avatar from "../ui/Avatar";
import { cx } from "../ui/cx";
import IconButton from "../ui/IconButton";
import Logo from "../ui/Logo";
import { NAVIGATION, ROLE_LABELS } from "./navigation";

/** Üst çubuk: ürün işareti, ana gezinme ve kullanıcı. Üniversite logosu giriş ekranındadır. */
export default function AppHeader({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  if (!user) return null;
  // Ders içindeyken: tutor bölümünde "AI Tutor", diğer ders sayfalarında "Derslerim" seçili
  // görünür; Hesabım sayfasında ikisi de seçili değildir (#106).
  const inTutor = pathname.endsWith("/tutor");
  const inAccount = pathname.endsWith("/account");

  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface px-5 text-ink sm:px-8">
      <IconButton icon={Menu} label="Menüyü aç" onClick={onOpenMenu} className="-ml-1.5 md:hidden" />
      <Link to={homePath(user.role)} className="rounded-control py-1" aria-label="Ana sayfa">
        <Logo />
      </Link>

      <nav aria-label="Ana gezinme" className="ml-auto hidden h-full items-stretch gap-1 md:flex">
        {NAVIGATION[user.role].map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={() => {
              const isActive = !inAccount && (to.endsWith("/tutor") ? inTutor : !inTutor);
              return cx(
                "flex items-center border-b-3 px-3 pt-0.75 text-base font-semibold transition-colors",
                isActive
                  ? "border-accent text-accent"
                  : "border-transparent text-graphite hover:text-ink",
              );
            }}
          >
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2 md:ml-4 md:border-l md:border-line md:pl-5">
        <Link
          to={`${homePath(user.role)}/account`}
          className="flex items-center gap-3 rounded-control px-1.5 py-1 hover:bg-subtle"
          aria-label={`Hesabım: ${user.name}`}
        >
          <span className="hidden text-right sm:block">
            <span className="block text-sm leading-tight font-semibold">{user.name}</span>
            <span className="block text-xs text-graphite">{ROLE_LABELS[user.role]}</span>
          </span>
          <Avatar name={user.name} className="bg-accent text-on-accent" />
        </Link>
        <IconButton icon={LogOut} label="Çıkış yap" onClick={() => void logout()} />
      </div>
    </header>
  );
}
