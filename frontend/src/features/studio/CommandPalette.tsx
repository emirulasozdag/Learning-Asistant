import { ArrowRight, CornerDownLeft, FileText, MessageSquareText, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router";

import type { DocumentOut } from "../../api/types";
import { courseService } from "../../services/courseService";
import { cx } from "../../ui/cx";
import { buildCommands, flatten, type Command } from "./commands";

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  courseId: number;
  base: string;
  onAsk: (question: string) => void;
}

const ICONS = { ask: MessageSquareText, document: FileText, navigate: ArrowRight } as const;

/**
 * Ctrl K paleti: materyale soru sorma, belge ve bölüm arama. Ok tuşları satırları gezer, Enter
 * seçer, Escape kapatır. Belge listesi palet ilk açıldığında bir kez yüklenir.
 */
export default function CommandPalette({ open, onClose, courseId, base, onAsk }: CommandPaletteProps) {
  if (!open) return null;
  return createPortal(
    <PaletteDialog onClose={onClose} courseId={courseId} base={base} onAsk={onAsk} />,
    document.body,
  );
}

function PaletteDialog({ onClose, courseId, base, onAsk }: Omit<CommandPaletteProps, "open">) {
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    inputRef.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .materials(courseId, controller.signal)
      .then((list) => {
        if (!controller.signal.aborted) setDocuments(list);
      })
      .catch(() => {
        // Belgeler gelmezse palet yine de soru ve gezinme için çalışır.
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [courseId]);

  const groups = useMemo(() => buildCommands(query, base, documents), [query, base, documents]);
  const commands = useMemo(() => flatten(groups), [groups]);
  const active = Math.min(cursor, Math.max(commands.length - 1, 0));

  function run(command: Command) {
    onClose();
    if (command.kind === "ask") onAsk(command.question);
    else navigate(command.to);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (commands.length === 0) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setCursor((active + step + commands.length) % commands.length);
    } else if (event.key === "Enter" && commands[active]) {
      event.preventDefault();
      run(commands[active]);
    } else if (event.key === "Tab") {
      event.preventDefault();
      inputRef.current?.focus();
    }
  }

  const positions = new Map(commands.map((command, position) => [command.id, position]));
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[12vh]" onKeyDown={onKeyDown}>
      <div className="fade-in absolute inset-0 bg-ink/30" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Materyalde ara"
        className="fade-in relative w-full max-w-xl overflow-hidden rounded-panel border border-line bg-surface shadow-float"
      >
        <div className="flex items-center gap-3 border-b border-line px-4">
          <Search size={17} aria-hidden className="shrink-0 text-graphite" />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setCursor(0);
            }}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={commands[active] ? `${listId}-${commands[active].id}` : undefined}
            aria-label="Materyalde ara ya da soru yaz"
            placeholder="Materyalde ara ya da soru yaz"
            className="h-13 min-w-0 flex-1 bg-transparent text-md text-ink placeholder:text-faint focus:outline-none"
          />
          <kbd className="rounded-[3px] border border-line px-1.5 py-0.5 font-mono text-xs text-graphite">Esc</kbd>
        </div>

        <div id={listId} role="listbox" aria-label="Sonuçlar" className="max-h-[52vh] overflow-y-auto py-2">
          {groups.map((group) => (
            <div key={group.title} role="group" aria-label={group.title} className="px-2 pb-1">
              <p className="px-2 pt-2 pb-1 text-xs font-medium text-graphite">{group.title}</p>
              {group.commands.map((command) => {
                const position = positions.get(command.id) ?? 0;
                const selected = position === active;
                const Icon = ICONS[command.kind];
                return (
                  <div
                    key={command.id}
                    id={`${listId}-${command.id}`}
                    role="option"
                    aria-selected={selected}
                    onMouseMove={() => setCursor(position)}
                    onClick={() => run(command)}
                    className={cx(
                      "flex cursor-pointer items-center gap-3 rounded-control px-2 py-2 text-base",
                      selected ? "bg-accent-soft text-ink" : "text-ink-2",
                    )}
                  >
                    <Icon size={15} aria-hidden className={selected ? "text-accent" : "text-graphite"} />
                    <span className="min-w-0 flex-1 truncate">{command.label}</span>
                    {command.kind !== "ask" && <span className="shrink-0 text-xs text-graphite">{command.hint}</span>}
                    {selected && <CornerDownLeft size={13} aria-hidden className="shrink-0 text-graphite" />}
                  </div>
                );
              })}
            </div>
          ))}
          {commands.length === 0 && (
            <p className="px-4 py-6 text-center text-base text-graphite">
              {loading ? "Belgeler yükleniyor…" : "Eşleşen bir sonuç yok."}
            </p>
          )}
        </div>

        <div className="flex items-center gap-4 border-t border-line bg-canvas/60 px-4 py-2 text-xs text-graphite">
          <span>
            <kbd className="font-mono">↑ ↓</kbd> gez
          </span>
          <span>
            <kbd className="font-mono">Enter</kbd> seç
          </span>
          <span className="ml-auto">Yalnızca bu dersin onaylı materyali</span>
        </div>
      </div>
    </div>
  );
}
