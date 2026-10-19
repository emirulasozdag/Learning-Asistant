import { Fragment, type ReactNode } from "react";

import { cx } from "./cx";

export interface Stat {
  label: string;
  value: ReactNode;
  /** Değerin altında küçük açıklama (ör. "%48"). */
  hint?: ReactNode;
}

/** Yatay sayı satırı: kart kullanmadan, ince ayraçlarla. Dar ekranda alta kayar. */
export default function StatRow({ stats, className }: { stats: Stat[]; className?: string }) {
  return (
    <dl className={cx("flex flex-wrap items-stretch gap-y-4", className)}>
      {stats.map((stat, index) => (
        <Fragment key={stat.label}>
          {index > 0 && <span aria-hidden className="mx-6 hidden w-px bg-line sm:block" />}
          <div className="flex min-w-[7.5rem] flex-col-reverse pr-6 sm:pr-0">
            <dt className="text-sm text-graphite">
              {stat.label}
              {stat.hint && <span className="ml-1.5 text-faint">{stat.hint}</span>}
            </dt>
            <dd className="text-[1.75rem] leading-tight font-bold text-ink tabular-nums">{stat.value}</dd>
          </div>
        </Fragment>
      ))}
    </dl>
  );
}
