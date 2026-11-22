import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cx } from "./cx";

/** Veri tablosu: sakin başlık satırı, ince satır çizgileri, tıklanabilir satırda hover vurgusu. */
export function Table({ children, label }: { children: ReactNode; label: string }) {
  return (
    <div className="overflow-x-auto rounded-panel border border-line bg-surface">
      <table aria-label={label} className="w-full border-collapse text-left text-base">
        {children}
      </table>
    </div>
  );
}

export function THead({ children }: { children: ReactNode }) {
  return <thead className="border-b border-line bg-subtle text-graphite">{children}</thead>;
}

export function TH({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cx("h-11 px-4 text-sm font-semibold whitespace-nowrap", className)}
      {...props}
    />
  );
}

export function TR({
  className,
  interactive,
  selected,
  ...props
}: HTMLAttributes<HTMLTableRowElement> & { interactive?: boolean; selected?: boolean }) {
  return (
    <tr
      className={cx(
        "border-b border-line last:border-b-0",
        interactive && "cursor-pointer transition-colors hover:bg-accent-soft/50",
        selected && "bg-accent-soft/50",
        className,
      )}
      {...props}
    />
  );
}

export function TD({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx("h-14 px-4 py-2.5 align-middle", className)} {...props} />;
}
