import type { HTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";

type CardVariant = "plain" | "inset" | "callout";
type CardPadding = "none" | "sm" | "md";

const VARIANTS: Record<CardVariant, string> = {
  plain: "border border-line bg-surface",
  // Kart içindeki ikincil alan (ör. alıntı, örnek); çizgisiz.
  inset: "bg-subtle",
  // Sayfadaki tek çağrı (ör. "AI Tutor'a soru sor"): solda lacivert çizgi.
  callout: "border border-line border-l-4 border-l-accent bg-surface",
};

const PADDINGS: Record<CardPadding, string> = {
  none: "",
  sm: "px-4 py-3",
  md: "px-5 py-5 sm:px-6",
};

/**
 * Bütün kartların tek biçimi. Gölge yoktur (gölge yalnızca yüzen katmanlarda); tıklanabilir kart
 * `interactive` ile hover'da lacivert çerçeve alır.
 */
export default function Card({
  as: Tag = "div",
  variant = "plain",
  padding = "md",
  interactive = false,
  className,
  children,
  ...props
}: HTMLAttributes<HTMLElement> & {
  as?: "div" | "section" | "article" | "li" | "aside";
  variant?: CardVariant;
  padding?: CardPadding;
  interactive?: boolean;
  children?: ReactNode;
}) {
  return (
    <Tag
      className={cx(
        "rounded-panel",
        VARIANTS[variant],
        PADDINGS[padding],
        interactive && "transition-colors hover:border-accent-line hover:bg-accent-soft/40",
        className,
      )}
      {...props}
    >
      {children}
    </Tag>
  );
}
