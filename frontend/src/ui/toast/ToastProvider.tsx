import { CircleAlert, CircleCheck, Info, X } from "lucide-react";
import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";

import { cx } from "../cx";
import { ToastContext, type ToastInput } from "./context";

interface Toast extends ToastInput {
  id: number;
}

const DURATION_MS = 4500;
const ICONS = { success: CircleCheck, danger: CircleAlert, neutral: Info };
const ICON_TONES = { success: "text-success", danger: "text-danger", neutral: "text-graphite" };

/** Sağ altta üst üste dizilen bildirimler; ekran okuyucuya da duyurulur. */
export default function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(0);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (input: ToastInput) => {
      const id = ++nextId.current;
      setToasts((list) => [...list.slice(-2), { ...input, id }]);
      window.setTimeout(() => dismiss(id), DURATION_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        // role="log": eklenen bildirimler kibarca duyurulur; sayfanın kendi durum bölgesiyle karışmaz.
        role="log"
        aria-label="Bildirimler"
        className="pointer-events-none fixed right-4 bottom-4 z-50 flex w-[22rem] max-w-[calc(100vw-2rem)] flex-col gap-2"
      >
        {toasts.map((toast) => {
          const tone = toast.tone ?? "neutral";
          const Icon = ICONS[tone];
          return (
            <div
              key={toast.id}
              className="slide-in-right pointer-events-auto flex items-start gap-3 rounded-panel border border-line bg-surface px-4 py-3 shadow-float"
            >
              <Icon size={18} aria-hidden className={cx("mt-0.5 shrink-0", ICON_TONES[tone])} />
              <div className="min-w-0 flex-1">
                <p className="text-base font-semibold text-ink">{toast.title}</p>
                {toast.description && <p className="mt-0.5 text-sm text-graphite">{toast.description}</p>}
              </div>
              <button
                type="button"
                onClick={() => dismiss(toast.id)}
                aria-label="Bildirimi kapat"
                className="-mt-0.5 -mr-1 flex size-7 shrink-0 items-center justify-center rounded-control text-faint hover:bg-subtle hover:text-ink"
              >
                <X size={14} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
