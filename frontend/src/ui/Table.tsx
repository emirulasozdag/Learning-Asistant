import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from "react";

import { cx } from "./cx";

/** Sade veri tablosu: çerçeveli tek panel, satır çizgileri, hover vurgusu. */
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
  return <thead className="border-b border-line bg-canvas/70">{children}</thead>;
}

export function TH({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cx("h-9 px-4 text-sm font-medium whitespace-nowrap text-graphite", className)}
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
        interactive && "cursor-pointer transition-colors hover:bg-canvas",
        selected && "bg-accent-soft/50",
        className,
      )}
      {...props}
    />
  );
}

export function TD({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cx("h-12 px-4 align-middle", className)} {...props} />;
}
