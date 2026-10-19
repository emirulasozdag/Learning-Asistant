import { useEffect, useRef, useState, type ReactNode } from "react";

import SourcePanel from "./SourcePanel";
import { useIsDesktop } from "./useIsDesktop";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

/**
 * Seçilen kaynağı gösterir. Geniş ekranda yanda sabit bir panel, dar ekranda tam ekran bir
 * diyalog olarak açılır; ikisi aynı anda render edilmez. Kapanınca odak, paneli açan
 * düğmeye (o artık yoksa soru alanına) geri döner.
 */
export default function SourceViewer({ sourceId, onClose }: { sourceId: string; onClose: () => void }) {
  const desktop = useIsDesktop();
  // Render sırasında okunur: alt bileşenlerin efektleri odağı panele taşımadan önce.
  const [opener] = useState(() => document.activeElement as HTMLElement | null);

  useEffect(
    () => () => {
      const target =
        opener && opener !== document.body && opener.isConnected
          ? opener
          : document.getElementById("tutor-question");
      target?.focus();
    },
    [opener],
  );

  // `key`: kaynak değişince eski içerik ve eski hata temizlenir.
  if (desktop) {
    return (
      <div className="w-[min(46%,560px)] shrink-0 border-l border-line">
        <SourcePanel key={sourceId} sourceId={sourceId} onClose={onClose} />
      </div>
    );
  }
  return (
    <ModalFrame onClose={onClose}>
      <SourcePanel key={sourceId} sourceId={sourceId} onClose={onClose} modal />
    </ModalFrame>
  );
}

/** Dar ekranda tam ekran diyalog: odak içeride kalır, Escape ve arka plana tıklama kapatır. */
function ModalFrame({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);

  useEffect(() => {
    closeRef.current = onClose;
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const items = [...dialog.querySelectorAll<HTMLElement>(FOCUSABLE)];
      if (items.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      const active = document.activeElement;
      if (!dialog.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || active === dialog)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="fixed inset-0 z-40">
      <div className="fade-in absolute inset-0 bg-ink/25" onClick={onClose} aria-hidden />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label="Kaynak"
        tabIndex={-1}
        className="slide-in-right absolute inset-y-0 right-0 w-full max-w-md shadow-float focus:outline-none"
      >
        {children}
      </div>
    </div>
  );
}
