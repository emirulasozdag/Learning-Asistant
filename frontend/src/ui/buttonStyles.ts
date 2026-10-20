import { cx } from "./cx";

export type Variant = "primary" | "secondary" | "ghost" | "danger";
export type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-on-accent shadow-sm hover:bg-accent-hover disabled:bg-muted-bg disabled:text-faint disabled:shadow-none",
  secondary:
    "border border-line bg-surface text-ink hover:border-line-strong hover:bg-subtle disabled:text-faint",
  ghost: "text-ink-2 hover:bg-subtle hover:text-ink disabled:text-faint",
  danger: "border border-line bg-surface text-danger hover:border-danger/40 hover:bg-danger-soft",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-sm",
  md: "h-9 gap-2 px-3.5 text-base",
  lg: "h-11 gap-2 px-5 text-md",
};

export function buttonClasses(variant: Variant = "secondary", size: Size = "md"): string {
  return cx(
    "inline-flex shrink-0 items-center justify-center rounded-control font-medium whitespace-nowrap transition-colors disabled:cursor-not-allowed",
    VARIANTS[variant],
    SIZES[size],
  );
}
