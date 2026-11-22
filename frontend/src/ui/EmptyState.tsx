import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "danger";
  /** Başlık seviyesi: tam sayfa durumunda sayfanın tek h1'i olur (varsayılan h3). */
  level?: 1 | 2 | 3;
  className?: string;
}

/** Boş ya da hata durumu: ne olduğunu ve ne yapılacağını söyler. */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "neutral",
  level = 3,
  className,
}: EmptyStateProps) {
  const Heading = `h${level}` as "h1" | "h2" | "h3";
  return (
    <div className={cx("flex flex-col items-center px-6 py-14 text-center", className)}>
      <span
        className={cx(
          "mb-4 flex size-12 items-center justify-center rounded-full",
          tone === "danger" ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent",
        )}
      >
        <Icon size={20} aria-hidden />
      </span>
      <Heading className="text-lg font-semibold text-ink">{title}</Heading>
      {description && <p className="mt-1.5 max-w-md text-base text-graphite">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
