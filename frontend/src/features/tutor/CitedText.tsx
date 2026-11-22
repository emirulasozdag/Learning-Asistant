import type { Citation } from "../../api/types";
import { citationLabel } from "../../labels";
import { cx } from "../../ui/cx";
import type { SelectSourceProps } from "./types";

/**
 * Cevap metni: [1] (doğrulanmış) ya da [S1] (model yazarken) işaretleri tıklanabilir
 * dipnot işaretlerine (fosforlu üst simge) dönüşür.
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

/**
 * Dipnot işareti: tıklanınca kaynağı açan fosforlu üst simge (`.footnote-mark`). Sarı yalnızca
 * "bu bilgi ders materyalinden" demektir; açık kaynağın işareti lacivert halkayla belirginleşir.
 */
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
      aria-pressed={active}
      title={citationLabel(citation)}
      className={cx(
        "footnote-mark mx-0.5 cursor-pointer px-1 transition-shadow",
        active ? "ring-2 ring-accent" : "hover:ring-2 hover:ring-ink/25",
      )}
    >
      {number}
    </button>
  );
}

/** Tıklanmayan dipnot işareti (ör. bir düğmenin içinde). Ekran okuyucu kaynağı metinden okur. */
export function FootnoteMark({ number, className }: { number: number; className?: string }) {
  return (
    <span aria-hidden className={cx("footnote-mark px-1", className)}>
      {number}
    </span>
  );
}
