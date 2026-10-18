import { LogOut, PanelLeftClose, PanelLeftOpen, Plus } from "lucide-react";
import { NavLink } from "react-router";

import { useAuth } from "../auth/useAuth";
import { useCourses } from "../features/courses/context";
import { courseInitials } from "../labels";
import Avatar from "../ui/Avatar";
import { cx } from "../ui/cx";
import IconButton from "../ui/IconButton";
import Logo, { LogoMark } from "../ui/Logo";
import Skeleton from "../ui/Skeleton";
import { NAVIGATION, ROLE_LABELS, coursePath } from "./navigation";

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
  /** Mobilde çekmece olarak açıldığında: bir bağlantıya tıklanınca kapanır. */
  onNavigate?: () => void;
}

const itemClass = (active: boolean, collapsed: boolean) =>
  cx(
    "group flex h-8 items-center gap-2.5 rounded-control text-base transition-colors",
    collapsed ? "justify-center px-0" : "px-2.5",
    active
      ? "bg-muted-bg/80 font-medium text-ink"
      : "text-ink-2 hover:bg-subtle hover:text-ink",
  );

export default function Sidebar({ collapsed, onToggle, onNavigate }: SidebarProps) {
  const { user, logout } = useAuth();
  const { courses, loading, openCreate } = useCourses();
  if (!user) return null;

  return (
    <aside
      aria-label="Ana menü"
      className={cx(
        "flex h-full shrink-0 flex-col border-r border-line bg-surface transition-[width] duration-200",
        collapsed ? "w-14" : "w-60",
      )}
    >
      <div className={cx("flex h-14 items-center", collapsed ? "justify-center" : "justify-between px-4")}>
        {collapsed ? <LogoMark className="text-ink" /> : <Logo />}
        {!collapsed && (
          <IconButton icon={PanelLeftClose} label="Menüyü daralt" size="sm" onClick={onToggle} />
        )}
      </div>

      <nav className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 pt-2">
        {NAVIGATION[user.role].map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            title={collapsed ? label : undefined}
            className={({ isActive }) => itemClass(isActive, collapsed)}
          >
            {({ isActive }) => (
              <>
                <Icon size={16} aria-hidden className={isActive ? "text-accent" : "text-graphite"} />
                {!collapsed && label}
              </>
            )}
          </NavLink>
        ))}

        <div className={cx("mt-6 mb-1 flex items-center justify-between", collapsed ? "px-0" : "px-2.5")}>
          {!collapsed && <span className="text-sm text-faint">Derslerim</span>}
          {user.role === "instructor" && !collapsed && (
            <IconButton icon={Plus} label="Ders oluştur" size="sm" onClick={openCreate} />
          )}
        </div>
        {loading && !collapsed && (
          <div className="flex flex-col gap-2 px-2.5 py-1">
            <Skeleton className="h-3 w-3/4" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        )}
        {courses.map((course) => (
          <NavLink
            key={course.id}
            to={coursePath(user.role, course.id)}
            onClick={onNavigate}
            title={collapsed ? `${course.code} ${course.name}` : undefined}
            className={({ isActive }) => itemClass(isActive, collapsed)}
          >
            {({ isActive }) => (
              <>
                <span
                  aria-hidden
                  className={cx(
                    "flex size-5 shrink-0 items-center justify-center rounded text-[10px] font-semibold",
                    isActive ? "bg-accent text-white" : "bg-subtle text-graphite",
                  )}
                >
                  {courseInitials(course.name)}
                </span>
                {!collapsed && <span className="truncate">{course.name}</span>}
              </>
            )}
          </NavLink>
        ))}
        {!loading && courses.length === 0 && !collapsed && (
          <p className="px-2.5 py-1 text-sm text-faint">
            {user.role === "instructor" ? "Henüz ders yok." : "Kayıtlı ders yok."}
          </p>
        )}
      </nav>

      <div className="border-t border-line p-2">
        {collapsed ? (
          <div className="flex flex-col items-center gap-1">
            <IconButton icon={PanelLeftOpen} label="Menüyü genişlet" onClick={onToggle} />
            <IconButton icon={LogOut} label="Çıkış yap" onClick={logout} />
          </div>
        ) : (
          <div className="flex items-center gap-2.5 rounded-control px-2 py-1.5">
            <Avatar name={user.name} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-base font-medium text-ink">{user.name}</p>
              <p className="truncate text-sm text-graphite">{ROLE_LABELS[user.role]}</p>
            </div>
            <IconButton icon={LogOut} label="Çıkış yap" size="sm" onClick={logout} />
          </div>
        )}
      </div>
    </aside>
  );
}
