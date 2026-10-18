import { LoaderCircle, type LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { buttonClasses, type Size, type Variant } from "./buttonStyles";
import { cx } from "./cx";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  /** Sağda gösterilecek ikon (ör. dış bağlantı). */
  trailingIcon?: LucideIcon;
  loading?: boolean;
  children?: ReactNode;
}

export default function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  trailingIcon: TrailingIcon,
  loading = false,
  disabled,
  className,
  children,
  type = "button",
  ...props
}: ButtonProps) {
  const iconSize = size === "lg" ? 16 : 14;
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cx(buttonClasses(variant, size), className)}
      {...props}
    >
      {loading ? (
        <LoaderCircle size={iconSize} className="animate-spin" aria-hidden />
      ) : (
        Icon && <Icon size={iconSize} aria-hidden />
      )}
      {children}
      {TrailingIcon && <TrailingIcon size={iconSize} aria-hidden className="opacity-70" />}
    </button>
  );
}
