import { LogOut, Menu } from "lucide-react";
import { Link, NavLink, useLocation } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import Avatar from "../ui/Avatar";
import { cx } from "../ui/cx";
import IconButton from "../ui/IconButton";
import Logo from "../ui/Logo";
import { NAVIGATION, ROLE_LABELS } from "./navigation";

/** Üst bar: ürün işareti, ana gezinme ve kullanıcı. */
export default function AppHeader({ onOpenMenu }: { onOpenMenu: () => void }) {
  const { user, logout } = useAuth();
  const { pathname } = useLocation();
  if (!user) return null;
  // Ders içindeyken: tutor bölümünde "AI Tutor", diğer ders sayfalarında "Derslerim" seçili
  // görünür; Hesabım sayfasında ikisi de seçili değildir (#106).
  const inTutor = pathname.endsWith("/tutor");
  const inAccount = pathname.endsWith("/account");

  return (
    <header className="flex h-[4.5rem] shrink-0 items-center gap-3 border-b border-line bg-surface/85 px-3 backdrop-blur sm:px-8">
      <IconButton icon={Menu} label="Menüyü aç" onClick={onOpenMenu} className="md:hidden" />
      {/* Uygulamanın içinde tek marka: ürün logosu. Üniversite adı giriş ekranındadır (#103). */}
      <Link to={homePath(user.role)} className="mr-4 rounded-control px-1 py-1 lg:mr-8" aria-label="Ana sayfa">
        <Logo />
      </Link>

      <nav aria-label="Ana gezinme" className="ml-auto hidden h-full items-stretch gap-2 md:flex">
        {NAVIGATION[user.role].map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={() => {
              const isActive = !inAccount && (to.endsWith("/tutor") ? inTutor : !inTutor);
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
        <Link
          to={`${homePath(user.role)}/account`}
          className="flex items-center gap-3 rounded-control px-1 py-1 hover:bg-subtle"
          aria-label={`Hesabım: ${user.name}`}
        >
          <span className="hidden text-right sm:block">
            <span className="block text-sm leading-tight font-semibold text-ink">{user.name}</span>
            <span className="block text-xs text-graphite">{ROLE_LABELS[user.role]}</span>
          </span>
          <Avatar name={user.name} className="bg-accent text-on-accent" />
        </Link>
        <IconButton icon={LogOut} label="Çıkış yap" onClick={() => void logout()} />
      </div>
    </header>
  );
}
