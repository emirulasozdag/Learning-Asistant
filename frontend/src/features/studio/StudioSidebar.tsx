import { LogOut } from "lucide-react";

import { useAuth } from "../../auth/useAuth";
import { coursePath } from "../../layouts/navigation";
import type { Course } from "../../services/courseService";
import ThemeSwitcher from "../../theme/ThemeSwitcher";
import Avatar from "../../ui/Avatar";
import { LogoMark, PRODUCT_NAME } from "../../ui/Logo";
import ConversationList from "./ConversationList";
import CourseSwitcher from "./CourseSwitcher";
import StudioNav from "./StudioNav";
import { useStudio } from "./useStudio";

/**
 * Çalışma alanının sol sütunu: kurum ve ürün, ders seçici, araçlar, bu sohbetin soruları ve
 * tema seçimi. Dar ekranda aynı içerik çekmece olarak açılır.
 */
export default function StudioSidebar({
  course,
  courses,
  onNavigate,
}: {
  course: Course;
  courses: Course[];
  onNavigate?: () => void;
}) {
  const { user, logout } = useAuth();
  const { entries, activeId, select } = useStudio();
  const role = user?.role ?? "student";
  const base = coursePath(role, course.id);

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto bg-subtle/60 px-4 pt-5 pb-4">
      <div className="flex items-center gap-2.5">
        <LogoMark className="size-8 text-accent" />
        <div className="min-w-0">
          <p className="text-base leading-tight font-bold text-ink">{PRODUCT_NAME}</p>
          <p className="font-mono text-[11px] text-graphite">yalnızca onaylı materyal</p>
        </div>
      </div>

      <CourseSwitcher
        course={course}
        courses={courses}
        pathFor={(item) => `${coursePath(role, item.id)}/tutor`}
        allCoursesPath={`/${role}`}
      />

      <StudioNav base={base} onNavigate={onNavigate} />

      <ConversationList
        entries={entries}
        activeId={activeId}
        onSelect={(id) => {
          select(id);
          onNavigate?.();
        }}
      />

      <div className="mt-auto flex flex-col gap-4 border-t border-line pt-4">
        <ThemeSwitcher />
        {user && (
          <div className="flex items-center gap-2.5 px-1">
            <Avatar name={user.name} size="sm" className="bg-accent text-on-accent" />
            <span className="min-w-0 flex-1 truncate text-sm text-ink-2">{user.name}</span>
            <button
              type="button"
              onClick={() => void logout()}
              aria-label="Çıkış yap"
              title="Çıkış yap"
              className="flex size-8 items-center justify-center rounded-control text-graphite hover:bg-subtle hover:text-ink"
            >
              <LogOut size={15} aria-hidden />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
