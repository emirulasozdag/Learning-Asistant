import type { Citation } from "../../api/types";
import { citationLabel } from "../../labels";
import { cx } from "../../ui/cx";
import type { SelectSourceProps } from "./types";

/**
 * Cevap metni: [1] (doğrulanmış) ya da [S1] (model yazarken) işaretleri tıklanabilir
 * fosforlu kalem numaralarına dönüşür.
 */
export default function CitedText({
  text,
  pattern,
  resolve,
  selectedSourceId,
  onSelectSource,
}: SelectSourceProps & {
  text: string;
  pattern: RegExp;
  resolve: (number: number) => Citation | undefined;
}) {
  return text.split(pattern).map((part, index) => {
    const number = Number(part.match(/\d+/)?.[0]);
    const citation = pattern.test(part) ? resolve(number) : undefined;
    if (!citation) return part;
    return (
      <CitationMark
        key={index}
        number={number}
        citation={citation}
        active={citation.source_id === selectedSourceId}
        onSelect={onSelectSource}
      />
    );
  });
}

/** Tıklanınca kaynağı açan fosforlu kalem numarası. */
export function CitationMark({
  number,
  citation,
  active,
  onSelect,
}: {
  number: number;
  citation: Citation;
  active: boolean;
  onSelect: (sourceId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(citation.source_id)}
      aria-label={`Kaynak ${number}: ${citationLabel(citation)}`}
      title={citationLabel(citation)}
      className={cx(
        "mx-0.5 inline-flex h-[18px] min-w-[18px] -translate-y-px items-center justify-center rounded-[3px] px-1 align-middle text-[11px] font-semibold text-ink tabular-nums transition-colors",
        active ? "bg-marker ring-1 ring-ink/70" : "bg-marker-soft hover:bg-marker",
      )}
    >
      {number}
    </button>
  );
}
