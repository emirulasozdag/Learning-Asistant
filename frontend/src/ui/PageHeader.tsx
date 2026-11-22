import type { ReactNode } from "react";

/** Sayfa içi bölüm başlığı (kartsız gruplama için). */
export function SectionHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-md font-semibold text-ink">{title}</h2>
        {description && <p className="mt-0.5 text-base text-graphite">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
