import { cx } from "./cx";

// Ürün adı tek yerden değiştirilir.
export const PRODUCT_NAME = "Learning Assistant";

/**
 * Ürün işareti: açık bir sayfa ve üzerinde işaretlenmiş bir satır —
 * "her cevap kaynağına bağlı" fikrinin kendisi.
 */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className={cx("size-6", className)}>
      <rect x="2" y="2" width="20" height="20" rx="5" fill="currentColor" />
      <rect x="6.5" y="7" width="11" height="1.6" rx="0.8" fill="white" opacity="0.55" />
      <rect x="6.5" y="11" width="11" height="2.6" rx="0.6" fill="var(--color-marker)" />
      <rect x="6.5" y="15.6" width="7.5" height="1.6" rx="0.8" fill="white" opacity="0.55" />
    </svg>
  );
}

/** "Learning Assistant": ilk kelime kalın, ikincisi ince — kurumsal sözcük işareti. */
function Wordmark() {
  const [first, ...rest] = PRODUCT_NAME.split(" ");
  return (
    <span className="text-lg leading-none tracking-tight">
      <span className="font-bold">{first}</span> <span className="font-light">{rest.join(" ")}</span>
    </span>
  );
}

export default function Logo({ className, onDark }: { className?: string; onDark?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-2", onDark ? "text-white" : "text-ink", className)}>
      <LogoMark className="text-accent" />
      <Wordmark />
    </span>
  );
}
