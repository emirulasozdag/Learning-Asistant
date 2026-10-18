import type { LucideIcon } from "lucide-react";

import { cx } from "./cx";

export interface SegmentOption<T extends string> {
  value: T;
  label: string;
  description?: string;
  icon?: LucideIcon;
}

interface SegmentedControlProps<T extends string> {
  name: string;
  label: string;
  options: SegmentOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** "cards": açıklamalı büyük seçenekler (ör. rol seçimi); "inline": kompakt. */
  variant?: "inline" | "cards";
}

/** Birbirini dışlayan seçenekler; klavye ile ok tuşlarıyla gezilebilir (radio grubu). */
export default function SegmentedControl<T extends string>({
  name,
  label,
  options,
  value,
  onChange,
  variant = "inline",
}: SegmentedControlProps<T>) {
  const cards = variant === "cards";
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-ink-2">{label}</legend>
      <div
        className={cx(
          cards
            ? "grid grid-cols-2 gap-2"
            : "inline-flex rounded-control border border-line bg-subtle p-0.5",
        )}
      >
        {options.map((option) => {
          const selected = option.value === value;
          const Icon = option.icon;
          return (
            <label
              key={option.value}
              className={cx(
                "cursor-pointer transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-accent",
                cards
                  ? cx(
                      "flex flex-col gap-1 rounded-panel border p-3",
                      selected
                        ? "border-accent bg-accent-soft/60 ring-1 ring-accent"
                        : "border-line bg-surface hover:border-line-strong",
                    )
                  : cx(
                      "flex h-7 items-center gap-1.5 rounded-[5px] px-3 text-sm",
                      selected
                        ? "bg-surface font-medium text-ink shadow-[0_1px_2px_rgb(20_26_38/0.08)]"
                        : "text-graphite hover:text-ink",
                    ),
              )}
            >
              <input
                type="radio"
                name={name}
                value={option.value}
                checked={selected}
                onChange={() => onChange(option.value)}
                className="sr-only"
              />
              {cards ? (
                <>
                  <span className="flex items-center gap-2 font-medium text-ink">
                    {Icon && (
                      <Icon size={16} aria-hidden className={selected ? "text-accent" : "text-graphite"} />
                    )}
                    {option.label}
                  </span>
                  {option.description && (
                    <span className="text-sm text-graphite">{option.description}</span>
                  )}
                </>
              ) : (
                <>
                  {Icon && <Icon size={14} aria-hidden />}
                  {option.label}
                </>
              )}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
