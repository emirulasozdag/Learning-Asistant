import { cx } from "./cx";

export type Variant = "primary" | "secondary" | "ghost" | "danger";
/** `icon`: yalnızca ikonlu yuvarlak düğme (ör. gönder); erişilebilir adı `aria-label` verir. */
export type Size = "sm" | "md" | "lg" | "icon";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-on-accent hover:bg-accent-hover disabled:bg-muted-bg disabled:text-faint",
  secondary:
    "border border-line-strong bg-surface text-ink hover:border-accent-line hover:bg-accent-soft hover:text-accent disabled:text-faint",
  ghost: "text-ink-2 hover:bg-subtle hover:text-ink disabled:text-faint",
  danger: "border border-line bg-surface text-danger hover:border-danger/40 hover:bg-danger-soft",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-sm",
  md: "h-10 gap-2 px-4 text-base",
  lg: "h-12 gap-2 px-5 text-md",
  icon: "size-10 rounded-full",
};

export function buttonClasses(variant: Variant = "secondary", size: Size = "md"): string {
  return cx(
    "inline-flex shrink-0 items-center justify-center rounded-control font-semibold whitespace-nowrap transition-colors disabled:cursor-not-allowed",
    VARIANTS[variant],
    SIZES[size],
  );
}
