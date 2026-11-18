import { forwardRef } from "react";

import { MAX_ANSWER_CHARS, type AnswerFeedback, type PracticeType } from "../../api/types";
import { cx } from "../../ui/cx";
import RichText from "../tutor/RichText";
import { optionLetter } from "./labels";

/**
 * Çoktan seçmeli şıklar. Cevaptan sonra doğru şık yeşil, seçilen yanlış şık kırmızı görünür.
 * `shortcuts`: şık harfi klavye kısayolu olarak gösterilir (pratik sayfası).
 */
export function ChoiceList({
  name,
  options,
  selected,
  onSelect,
  feedback,
  disabled,
  shortcuts = false,
}: {
  name: string;
  options: string[];
  selected: number | null;
  onSelect: (index: number) => void;
  feedback: AnswerFeedback | null;
  disabled: boolean;
  shortcuts?: boolean;
}) {
  return (
    <fieldset className="flex flex-col gap-2" disabled={disabled}>
      <legend className="sr-only">Seçenekler</legend>
      {options.map((option, index) => {
        const correct = feedback?.correct_option === index;
        const chosenWrong = feedback !== null && selected === index && !correct;
        return (
          <label
            key={index}
            className={cx(
              "relative flex cursor-pointer items-start gap-3 rounded-panel border px-3 py-2.5 text-base transition-colors",
              "has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
              correct
                ? "border-success bg-success-soft"
                : chosenWrong
                  ? "border-danger bg-danger-soft"
                  : selected === index
                    ? "border-accent bg-accent-soft/60"
                    : "border-line bg-surface hover:border-line-strong",
              feedback && "cursor-default",
            )}
          >
            {/* Görünmez ama tıklanabilir: tıklama doğrudan radyo düğmesine gelir, harf rozeti görsel. */}
            <input
              type="radio"
              name={name}
              className="absolute inset-0 size-full cursor-pointer opacity-0 disabled:cursor-default"
              checked={selected === index}
              onChange={() => onSelect(index)}
            />
            <span
              aria-hidden
              className={cx(
                "flex size-6 shrink-0 items-center justify-center rounded border text-xs font-semibold",
                correct
                  ? "border-success bg-success text-on-accent"
                  : chosenWrong
                    ? "border-danger bg-danger text-on-accent"
                    : selected === index
                      ? "border-accent bg-accent text-on-accent"
                      : "border-line-strong bg-surface text-graphite",
              )}
            >
              {optionLetter(index)}
            </span>
            <span className="min-w-0 flex-1 pt-0.5 text-ink">
              <span className="sr-only">{optionLetter(index)}) </span>
              <RichText text={option} inline />
            </span>
            {shortcuts && !feedback && (
              <kbd aria-hidden className="mt-0.5 hidden text-xs text-faint sm:inline">
                {index + 1}
              </kbd>
            )}
          </label>
        );
      })}
    </fieldset>
  );
}

/** Kısa cevap ve kod izleme için yazılı cevap alanı (backend sınırıyla aynı uzunlukta). */
export const AnswerText = forwardRef<
  HTMLTextAreaElement,
  {
    id?: string;
    type: PracticeType;
    value: string;
    onChange: (value: string) => void;
    disabled: boolean;
    onSubmitShortcut?: () => void;
    describedBy?: string;
  }
>(function AnswerText({ id, type, value, onChange, disabled, onSubmitShortcut, describedBy }, ref) {
  const code = type === "code_tracing";
  const remaining = MAX_ANSWER_CHARS - value.length;
  return (
    <div>
      <label htmlFor={id} className="sr-only">
        Cevabın
      </label>
      <textarea
        ref={ref}
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (onSubmitShortcut && event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
            event.preventDefault();
            onSubmitShortcut();
          }
        }}
        maxLength={MAX_ANSWER_CHARS}
        disabled={disabled}
        aria-describedby={describedBy}
        rows={code ? 6 : 4}
        placeholder={code ? "Çıktıyı ya da adımları yaz" : "Cevabını yaz"}
        className={cx(
          "w-full rounded-panel border border-line bg-surface px-3 py-2 text-base text-ink",
          "focus:border-accent focus:ring-3 focus:ring-accent/12 focus:outline-none disabled:bg-canvas",
          code && "font-mono text-sm",
        )}
      />
      {remaining < 300 && (
        <p className="mt-1 text-right text-xs text-graphite tabular-nums">{remaining} karakter kaldı</p>
      )}
    </div>
  );
});
