import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  tone?: "neutral" | "danger";
  className?: string;
}

/** Boş ya da hata durumu: ne olduğunu ve ne yapılacağını söyler. */
export default function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  tone = "neutral",
  className,
}: EmptyStateProps) {
  return (
    <div className={cx("flex flex-col items-center px-6 py-14 text-center", className)}>
      <span
        className={cx(
          "mb-4 flex size-10 items-center justify-center rounded-panel border",
          tone === "danger"
            ? "border-danger/20 bg-danger-soft text-danger"
            : "border-line bg-surface text-graphite",
        )}
      >
        <Icon size={18} aria-hidden />
      </span>
      <h3 className="text-md font-medium text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-base text-graphite">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
