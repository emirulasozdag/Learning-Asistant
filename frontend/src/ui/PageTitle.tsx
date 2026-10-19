import type { ReactNode } from "react";

import { cx } from "./cx";

/** Bölüm sayfasının başlığı: kalın başlık ve altında ince çizgi (OCW "Quizzes" başlığı gibi). */
export default function PageTitle({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={cx("mb-6 border-b border-line-strong pb-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <h1 className="text-[1.75rem] leading-tight font-bold tracking-tight text-ink">{title}</h1>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {description && <p className="mt-2 max-w-3xl text-md text-graphite">{description}</p>}
    </header>
  );
}
