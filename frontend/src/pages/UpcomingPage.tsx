import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import EmptyState from "../ui/EmptyState";

/**
 * Henüz geliştirilmekte olan bir bölüm. Ekip görevi: docs/UI_GOREVLERI.md.
 * Bu bileşen yalnızca yer tutar; bölüm yapılınca kaldırılır.
 */
export default function UpcomingPage({
  icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-panel border border-dashed border-line-strong bg-surface/60">
      <EmptyState icon={icon} title={title} description={description} action={action} />
    </div>
  );
}
