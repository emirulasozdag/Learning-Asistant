import { CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

type Tone = "info" | "success" | "warning" | "danger";

const TONES: Record<Tone, { box: string; icon: LucideIcon; iconColor: string }> = {
  info: { box: "border-accent-line bg-accent-soft", icon: Info, iconColor: "text-accent" },
  success: { box: "border-success/30 bg-success-soft", icon: CircleCheck, iconColor: "text-success" },
  warning: { box: "border-warning/30 bg-warning-soft", icon: TriangleAlert, iconColor: "text-warning" },
  danger: { box: "border-danger/30 bg-danger-soft", icon: CircleAlert, iconColor: "text-danger" },
};

/**
 * Sayfa içi bilgi ya da uyarı kutusu: ikon, isteğe bağlı başlık, metin ve eylem. Hata kutusu
 * `role="alert"`, diğerleri `role="note"` (ya da çağıranın verdiği rol) taşır.
 */
export default function Notice({
  tone = "info",
  title,
  children,
  action,
  role,
  className,
}: {
  tone?: Tone;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  role?: "alert" | "note" | "status";
  className?: string;
}) {
  const { box, icon: Icon, iconColor } = TONES[tone];
  return (
    <div
      role={role ?? (tone === "danger" ? "alert" : "note")}
      className={cx("flex flex-wrap items-start gap-3 rounded-panel border px-4 py-3", box, className)}
    >
      <Icon size={18} aria-hidden className={cx("mt-0.5 shrink-0", iconColor)} />
      <div className="min-w-0 flex-1 text-base text-ink">
        {title && <p className="font-semibold">{title}</p>}
        {children && <div className={cx(title ? "mt-0.5" : undefined, "text-ink-2")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
