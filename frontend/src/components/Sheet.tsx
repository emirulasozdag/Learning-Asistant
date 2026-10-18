import type { ReactNode } from "react";

interface SheetProps {
  /** Sol kenar boşluğunda gösterilen sayfa / slayt numarası. */
  page?: number | null;
  children: ReactNode;
}

/** Ders materyalinden bir sayfa: defter kâğıdı gibi, sayfa numarası kenar boşluğunda. */
export default function Sheet({ page, children }: SheetProps) {
  return (
    <div className="grid grid-cols-[3.25rem_1fr] rounded-sm bg-sheet shadow-[0_1px_2px_rgb(24_34_58/0.06),0_8px_24px_-12px_rgb(24_34_58/0.18)]">
      <div className="border-r border-margin pt-5 pr-2 text-right font-serif text-xs text-faint">
        {page ? `s. ${page}` : ""}
      </div>
      <div className="min-w-0 px-6 py-5 font-serif text-base">{children}</div>
    </div>
  );
}
