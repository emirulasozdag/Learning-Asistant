import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cx } from "./cx";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  /** Ekran okuyucu ve ipucu metni (zorunlu: ikon tek başına anlam taşımaz). */
  label: string;
  size?: "sm" | "md";
}

export default function IconButton({
  icon: Icon,
  label,
  size = "md",
  className,
  type = "button",
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      title={label}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-control text-graphite transition-colors hover:bg-subtle hover:text-ink disabled:cursor-not-allowed disabled:opacity-40",
        size === "sm" ? "size-7" : "size-8",
        className,
      )}
      {...props}
    >
      <Icon size={size === "sm" ? 14 : 16} aria-hidden />
    </button>
  );
}
