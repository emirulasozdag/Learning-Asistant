import type { SourceAlternative } from "../../api/types";
import { materialLabel } from "../../labels";

/**
 * Video alıntısının aynı içeriği anlatan doküman karşılıkları (slayt, ders notu).
 * Liste boşsa hiçbir şey çizilmez; seçilen kaynak aynı panelde açılır.
 */
export default function SourceAlternatives({
  alternatives,
  onSelect,
}: {
  alternatives: SourceAlternative[];
  onSelect: (sourceId: string) => void;
}) {
  if (alternatives.length === 0) return null;
  return (
    <section aria-labelledby="source-alternatives" className="mt-4">
      <h3 id="source-alternatives" className="text-sm font-medium text-ink">
        Aynı içerik dokümanda
      </h3>
      <ul className="mt-2 flex flex-col gap-1.5">
        {alternatives.map((alternative) => (
          <li key={alternative.source_id}>
            <button
              type="button"
              onClick={() => onSelect(alternative.source_id)}
              className="flex w-full items-baseline justify-between gap-3 rounded-control border border-line bg-surface px-3 py-2 text-left text-sm text-ink transition-colors hover:bg-subtle focus-visible:outline-2 focus-visible:outline-accent"
            >
              <span className="min-w-0 truncate">{alternative.document_title}</span>
              <span className="shrink-0 font-mono text-xs text-graphite">
                {alternative.page != null ? `s.${alternative.page}` : materialLabel(alternative.material_type)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
