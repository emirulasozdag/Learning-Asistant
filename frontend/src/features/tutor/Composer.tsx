import { ArrowUp, Square } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";

import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import { isDesktopNow } from "./useIsDesktop";

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
  /** Boş sohbette ekranın ortasında, daha büyük ve kendiliğinden odaklı. */
  prominent?: boolean;
}

const MAX_ROWS_HEIGHT = 200;

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
  prominent = false,
}: ComposerProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, MAX_ROWS_HEIGHT)}px`;
  }, [value]);

  useEffect(() => {
    // Yalnızca geniş ekranda: telefonda kendiliğinden odak klavyeyi açıp ekranı kapatır.
    if (prominent && !disabled && isDesktopNow()) ref.current?.focus({ preventScroll: true });
  }, [prominent, disabled]);

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
          "rounded-panel border bg-surface transition-[border-color,box-shadow]",
          "focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/10",
          disabled ? "border-line bg-subtle" : "border-line-strong",
        )}
      >
        <label htmlFor="tutor-question" className="sr-only">
          Sorun
        </label>
        <textarea
          id="tutor-question"
          ref={ref}
          rows={prominent ? 2 : 1}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          className={cx(
            "block max-h-[200px] w-full resize-none bg-transparent px-4 text-md leading-6 text-ink placeholder:text-faint focus:outline-none disabled:cursor-not-allowed",
            prominent ? "min-h-[60px] pt-3.5" : "min-h-11 pt-3",
          )}
        />
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5">
          <p className="hidden pl-1 text-xs text-faint sm:block">
            <kbd className="font-sans font-medium text-graphite">Enter</kbd> gönderir ·{" "}
            <kbd className="font-sans font-medium text-graphite">Shift + Enter</kbd> yeni satır
          </p>
          {busy && onStop ? (
            <Button size="icon" variant="secondary" onClick={onStop} aria-label="Durdur" title="Cevabı durdur" className="ml-auto">
              <Square size={14} fill="currentColor" aria-hidden />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              variant="primary"
              icon={ArrowUp}
              disabled={!canSend}
              aria-label="Gönder"
              title="Gönder"
              className="ml-auto"
            />
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-faint">{hint}</p>
    </form>
  );
}
