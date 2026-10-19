import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

import { cx } from "../../ui/cx";

interface ComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  busy?: boolean;
  /** Cevap sürerken gönder düğmesinin yerine "Durdur" gösterilir. */
  onStop?: () => void;
  placeholder: string;
  hint: string;
}

const MAX_ROWS_HEIGHT = 168;

/** Soru alanı: kendiliğinden uzar; Enter gönderir, Shift+Enter yeni satır. */
export default function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  onStop,
  placeholder,
  hint,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_ROWS_HEIGHT)}px`;
  }, [value]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (value.trim() && !busy) onSubmit();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (value.trim() && !busy) onSubmit();
    }
  }

  const canSend = Boolean(value.trim()) && !busy && !disabled;
  return (
    <form onSubmit={submit}>
      <div
        className={cx(
          "flex items-end gap-2 rounded-panel border bg-surface p-2 transition-colors focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/10",
          disabled ? "border-line bg-subtle" : "border-line-strong",
        )}
      >
        <label htmlFor="tutor-question" className="sr-only">
          Sorun
        </label>
        <textarea
          id="tutor-question"
          ref={ref}
          rows={1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className="max-h-[168px] min-h-9 flex-1 resize-none bg-transparent px-2 py-1.5 text-md text-ink placeholder:text-faint focus:outline-none disabled:cursor-not-allowed"
        />
        {busy && onStop ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Durdur"
            title="Cevabı durdur"
            className="flex size-9 shrink-0 items-center justify-center rounded-control bg-ink text-white transition-colors hover:bg-ink/85"
          >
            <Square size={14} fill="currentColor" aria-hidden />
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Gönder"
            className="flex size-9 shrink-0 items-center justify-center rounded-control bg-accent text-white transition-colors hover:bg-accent-hover disabled:bg-muted-bg disabled:text-faint"
          >
            <ArrowUp size={16} aria-hidden />
          </button>
        )}
      </div>
      <p className="mt-2 text-center text-xs text-faint">{hint}</p>
    </form>
  );
}
