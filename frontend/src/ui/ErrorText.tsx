import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

/** Form ya da işlem hatası: her yerde aynı boyut ve renkte, ekran okuyucuya hemen duyurulur. */
export default function ErrorText({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p role="alert" className={cx("flex items-start gap-1.5 text-sm text-danger", className)}>
      <CircleAlert size={15} aria-hidden className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
  );
}
