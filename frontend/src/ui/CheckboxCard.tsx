import type { ReactNode } from "react";

import { cx } from "./cx";

/**
 * Onay kutulu kart: kutu ve açıklaması tek bir tıklanabilir etiket. Aydınlatma metni, araştırma
 * kaydı ve materyal beyanı aynı biçimi kullanır.
 */
export default function CheckboxCard({
  checked,
  onChange,
  label,
  description,
  disabled,
  className,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: ReactNode;
  description?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label
      className={cx(
        "flex cursor-pointer items-start gap-3 rounded-panel border px-4 py-3.5 transition-colors",
        checked ? "border-accent-line bg-accent-soft/60" : "border-line bg-surface hover:border-line-strong",
        disabled && "cursor-not-allowed opacity-60",
        className,
      )}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="mt-0.5 size-4.5 shrink-0 accent-accent"
      />
      <span className="min-w-0">
        <span className="block text-base font-semibold text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-sm text-graphite">{description}</span>}
      </span>
    </label>
  );
}
