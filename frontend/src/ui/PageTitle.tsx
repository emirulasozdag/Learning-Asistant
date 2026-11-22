import type { ReactNode } from "react";

import { cx } from "./cx";
import { usePageTitle } from "./usePageTitle";

/** Bölüm sayfasının başlığı: kalın başlık ve altında ince çizgi (OCW "Quizzes" başlığı gibi).
 *
 * Başlık ölçeği: sayfa başlığı (h1) `text-2xl` (28px); sayfa içi bölüm başlığı (`level={2}`) `text-xl`,
 * bölüm içindeki grup başlıkları `text-lg`, panel başlıkları (`SectionHeader`, `InfoPanel`)
 * `text-md` yarı kalın. */
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
  // Sayfanın h1'i tarayıcı sekmesinin başlığıdır ("Takvim – Dipnot").
  usePageTitle(level === 1 && typeof title === "string" ? title : undefined);
  return (
    <header className={cx("mb-6 border-b border-line-strong pb-3", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <Heading
          className={cx(
            "leading-tight font-bold tracking-tight text-ink",
            level === 1 ? "text-2xl" : "text-xl",
          )}
        >
          {title}
        </Heading>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {description && <p className="mt-2 max-w-3xl text-md text-graphite">{description}</p>}
    </header>
  );
}
