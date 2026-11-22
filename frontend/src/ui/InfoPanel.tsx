import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";
import IconButton from "./IconButton";

export interface InfoSection {
  label: string;
  content: ReactNode;
}

/**
 * Sağ bilgi paneli (OCW "Course Info"): başlık, kapatma düğmesi ve etiketli bölümler. Boş
 * bölümler çağıran tarafta elenir.
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
      <div className="flex items-center justify-between border-b border-line py-2 pr-2 pl-5">
        <h2 className="text-md font-semibold text-ink">{title}</h2>
        {onClose && (
          <IconButton icon={X} label={`${title} panelini kapat`} onClick={onClose} />
        )}
      </div>
      <dl className="flex flex-col gap-5 px-5 py-5">
        {sections.map((section) => (
          <div key={section.label}>
            <dt className="text-sm font-semibold text-graphite">{section.label}</dt>
            <dd className="mt-1 text-base text-ink">{section.content}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}
