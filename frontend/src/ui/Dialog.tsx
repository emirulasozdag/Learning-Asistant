import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { cx } from "./cx";
import IconButton from "./IconButton";

interface OverlayProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}

/** Odak içeride kalır, Escape ve arka plana tıklama kapatır, açılmadan önceki odak geri gelir. */
function useOverlay(open: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const focusable = () =>
      [
        ...(panel?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? []),
      ].filter((element) => !element.hasAttribute("disabled"));
    (focusable().find((el) => el.dataset.autofocus !== undefined) ?? focusable()[1] ?? panel)?.focus();

    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab") return;
      const items = focusable();
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      previous?.focus();
    };
  }, [open, onClose]);
  return panelRef;
}

/** Ortada açılan diyalog (ör. ders oluşturma). Uzun içerik kendi içinde kayar. */
export default function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
}: OverlayProps & { size?: "md" | "lg" }) {
  const panelRef = useOverlay(open, onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[8vh]">
      <div className="fade-in absolute inset-0 bg-ink/25" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        tabIndex={-1}
        className={cx(
          "fade-in relative flex max-h-[86vh] w-full flex-col rounded-panel border border-line bg-surface shadow-float",
          size === "lg" ? "max-w-2xl" : "max-w-md",
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div>
            <h2 id="dialog-title" className="text-lg font-bold text-ink">
              {title}
            </h2>
            {description && <p className="mt-1 text-base text-graphite">{description}</p>}
          </div>
          <IconButton icon={X} label="Kapat" size="sm" onClick={onClose} />
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-4">{children}</div>
        {footer && (
          <div className="flex justify-end gap-2 border-t border-line bg-canvas/60 px-5 py-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

/** Sağdan açılan çekmece (ör. doküman ayrıntısı). */
export function Drawer({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "max-w-xl",
}: OverlayProps & { width?: string }) {
  const panelRef = useOverlay(open, onClose);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fade-in absolute inset-0 bg-ink/20" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="drawer-title"
        tabIndex={-1}
        className={cx(
          "slide-in-right relative flex h-full w-full flex-col border-l border-line bg-surface shadow-float",
          width,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
          <div className="min-w-0">
            <h2 id="drawer-title" className="truncate text-md font-semibold text-ink">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-base text-graphite">{description}</p>}
          </div>
          <IconButton icon={X} label="Kapat" size="sm" onClick={onClose} />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-6 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}
