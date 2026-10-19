import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

import { cx } from "./cx";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: LucideIcon;
  /** Ekran okuyucu ve ipucu metni (zorunlu: ikon tek başına anlam taşımaz). */
  label: string;
  size?: "sm" | "md";
  /** "dark": koyu lacivert menü üzerinde. */
  tone?: "default" | "dark";
}

export default function IconButton({
  icon: Icon,
  label,
  size = "md",
  tone = "default",
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
        "inline-flex shrink-0 items-center justify-center rounded-control transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        tone === "dark"
          ? "text-nav-muted hover:bg-white/10 hover:text-white"
          : "text-graphite hover:bg-subtle hover:text-ink",
        size === "sm" ? "size-7" : "size-8",
        className,
      )}
      {...props}
    >
      <Icon size={size === "sm" ? 14 : 16} aria-hidden />
    </button>
  );
}
