import { CircleAlert, CircleCheck, CircleDashed, SearchX } from "lucide-react";

import { cx } from "../../ui/cx";
import type { ConversationEntry } from "./context";

const STATE_ICON = {
  pending: { icon: CircleDashed, label: "cevap bekleniyor", tone: "text-graphite" },
  answered: { icon: CircleCheck, label: "kaynaklı cevap", tone: "text-success" },
  declined: { icon: SearchX, label: "materyalde yok", tone: "text-graphite" },
  failed: { icon: CircleAlert, label: "cevaplanamadı", tone: "text-warning" },
} as const;

/** "Bu sohbet": sorulan sorular; birine dokununca o soru ve kaynağı ortaya gelir. */
export default function ConversationList({
  entries,
  activeId,
  onSelect,
}: {
  entries: ConversationEntry[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <section aria-labelledby="conversation-list-title">
      <p id="conversation-list-title" className="mb-1.5 px-1 text-xs font-medium text-graphite">
        Bu sohbet
      </p>
      {entries.length === 0 ? (
        <p className="px-1 text-sm text-faint">Henüz soru sorulmadı.</p>
      ) : (
        <ol className="flex flex-col gap-0.5">
          {entries.map((entry) => {
            const state = STATE_ICON[entry.state];
            const active = entry.id === activeId;
            return (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => onSelect(entry.id)}
                  aria-current={active ? "true" : undefined}
                  className={cx(
                    "flex w-full items-start gap-2 rounded-control px-2 py-1.5 text-left text-sm transition-colors",
                    active ? "bg-subtle text-ink" : "text-ink-2 hover:bg-subtle hover:text-ink",
                  )}
                >
                  <state.icon size={14} aria-label={state.label} className={cx("mt-0.5 shrink-0", state.tone)} />
                  <span className="line-clamp-2 min-w-0">{entry.question}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
