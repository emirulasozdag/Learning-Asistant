import { cx } from "./cx";

// Ürün adı tek yerden değiştirilir.
export const PRODUCT_NAME = "Dipnot";

/**
 * Ürün işareti: küçük harf "d" ve sağ üstte fosforlu bir dipnot noktası — "her cevabın bir
 * dipnotu var" fikri. `inverse`: lacivert zemin üzerinde (üst çubuk) beyaz kare, lacivert harf.
 */
export function LogoMark({ className, inverse = false }: { className?: string; inverse?: boolean }) {
  const square = inverse ? "var(--color-chrome-ink)" : "var(--color-accent)";
  const letter = inverse ? "var(--color-chrome)" : "var(--color-on-accent)";
  return (
    <svg viewBox="0 0 32 32" aria-hidden className={cx("size-7 shrink-0", className)}>
      <rect width="32" height="32" rx="8" fill={square} />
      <circle cx="13.5" cy="19" r="5.6" fill="none" stroke={letter} strokeWidth="3.2" />
      <path d="M19.1 7.5v17.2" fill="none" stroke={letter} strokeWidth="3.2" strokeLinecap="round" />
      <circle cx="25.2" cy="7.2" r="4.4" fill="#ffd23f" />
    </svg>
  );
}

/**
 * "dipnot" sözcük işareti ve ürünün işareti. `inverse`: lacivert üst çubukta beyaz.
 * `subtitle`: işaretin altında küçük kurum adı (giriş ekranı).
 */
export default function Logo({
  className,
  inverse = false,
  subtitle,
}: {
  className?: string;
  inverse?: boolean;
  subtitle?: string;
}) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", inverse ? "text-chrome-ink" : "text-ink", className)}>
      <LogoMark inverse={inverse} />
      <span className="flex flex-col">
        <span className="text-xl leading-none font-bold tracking-tight">{PRODUCT_NAME.toLocaleLowerCase("tr")}</span>
        {subtitle && (
          <span className={cx("mt-1 text-xs leading-none", inverse ? "text-chrome-muted" : "text-graphite")}>
            {subtitle}
          </span>
        )}
      </span>
    </span>
  );
}
