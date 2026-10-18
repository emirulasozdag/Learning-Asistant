import type { ReactNode } from "react";

import { cx } from "./cx";

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Başlığın üstünde küçük bağlam (ör. ders kodu). */
  context?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

/** Sayfanın kimliği: başlık, kısa açıklama ve birincil eylemler. */
export default function PageHeader({
  title,
  description,
  context,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header className={cx("flex flex-wrap items-end justify-between gap-x-6 gap-y-4", className)}>
      <div className="min-w-0">
        {context && <div className="mb-2 flex items-center gap-2 text-sm text-graphite">{context}</div>}
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        {description && <p className="mt-1.5 max-w-2xl text-md text-graphite">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </header>
  );
}

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
