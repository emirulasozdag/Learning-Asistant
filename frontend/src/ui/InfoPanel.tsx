import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

export interface InfoSection {
  label: string;
  content: ReactNode;
}

/**
 * Sağ bilgi paneli (OCW "Course Info"): başlık şeridi, kapatma düğmesi ve küçük büyük harfli
 * başlıklarla bölümler. Boş bölümler çağıran tarafta elenir.
 */
export default function InfoPanel({
  title,
  sections,
  onClose,
  className,
}: {
  title: string;
  sections: InfoSection[];
  onClose?: () => void;
  className?: string;
}) {
  return (
    <aside aria-label={title} className={cx("rounded-panel border border-line bg-surface", className)}>
      <div className="flex items-center justify-between border-b border-line bg-subtle/70 py-1 pr-1 pl-5">
        <h2 className="text-md font-bold text-ink">{title}</h2>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label={`${title} panelini kapat`}
            className="flex size-10 items-center justify-center rounded-control text-ink hover:bg-muted-bg"
          >
            <X size={20} aria-hidden strokeWidth={2.5} />
          </button>
        )}
      </div>
      <dl className="flex flex-col gap-6 px-5 py-5">
        {sections.map((section) => (
          <div key={section.label}>
            <dt className="text-sm font-bold tracking-wide text-ink uppercase">{section.label}</dt>
            <dd className="mt-2 text-base text-ink-2">{section.content}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}
