import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";

import CommandPalette from "./CommandPalette";
import { StudioContext, type ConversationEntry, type StudioContextValue } from "./context";

/**
 * AI Tutor'un ders çerçevesindeki ortak durumu (#103): "Bu sohbet" listesi ve Ctrl/⌘+K ile açılan
 * materyal araması. Eskiden ayrı bir çalışma alanı kabuğundaydı; artık her ders sayfasında aynı
 * çerçevenin içinde (`CourseShell`) yaşar, sayfa düzeni sekmeler arasında değişmez.
 */
export default function StudioProvider({
  courseId,
  base,
  tutorPath,
  children,
}: {
  courseId: number;
  /** Dersin ana adresi (ör. /student/courses/4). */
  base: string;
  /** Komut paletinden soru sorulunca gidilecek AI Tutor adresi. */
  tutorPath: string;
  children: ReactNode;
}) {
  const [entries, setEntries] = useState<ConversationEntry[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [queuedQuestion, setQueuedQuestion] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const selectHandler = useRef<((id: string) => void) | null>(null);
  const navigate = useNavigate();
  const { pathname } = useLocation();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const publish = useCallback((list: ConversationEntry[], active: string | null) => {
    setEntries(list);
    setActiveId(active);
  }, []);

  const value = useMemo<StudioContextValue>(
    () => ({
      entries,
      activeId,
      publish,
      select: (id) => selectHandler.current?.(id),
      onSelect: (handler) => {
        selectHandler.current = handler;
      },
      queuedQuestion,
      queueQuestion: setQueuedQuestion,
      openSearch: () => setPaletteOpen(true),
      tutorPath,
    }),
    [entries, activeId, publish, queuedQuestion, tutorPath],
  );

  return (
    <StudioContext.Provider value={value}>
      {children}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        courseId={courseId}
        base={base}
        onAsk={(question) => {
          // Soru AI Tutor'da sorulur; başka bir ders sayfasındaysa oraya geçilir.
          setQueuedQuestion(question);
          if (!pathname.startsWith(tutorPath)) navigate(tutorPath);
        }}
      />
    </StudioContext.Provider>
  );
}
