import { cx } from "./cx";

/** Yüklenirken içeriğin yerini tutan gri blok. */
export default function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cx("skeleton block rounded", className)} />;
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div role="status" aria-label="Yükleniyor" className="flex flex-col gap-3 py-2">
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-3">
          <Skeleton className="size-8" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3 w-2/5" />
            <Skeleton className="h-2.5 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}
