import type { ReactNode } from "react";

import { cx } from "./cx";

/** Bölüm sayfasının başlığı: kalın başlık ve altında ince çizgi (OCW "Quizzes" başlığı gibi). */
export default function PageTitle({
  title,
  description,
  actions,
  level = 1,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  /** Sayfada tek h1 olur; aynı sayfadaki diğer bölüm başlıkları `level={2}` (#106). */
  level?: 1 | 2;
  className?: string;
}) {
  const Heading = level === 1 ? "h1" : "h2";
  return (
    <header className={cx("mb-6 border-b border-line-strong pb-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <Heading className="text-[1.75rem] leading-tight font-bold tracking-tight text-ink">{title}</Heading>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {description && <p className="mt-2 max-w-3xl text-md text-graphite">{description}</p>}
    </header>
  );
}
