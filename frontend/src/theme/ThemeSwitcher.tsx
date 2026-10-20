import { Check } from "lucide-react";
import { useRef, type KeyboardEvent } from "react";

import { cx } from "../ui/cx";
import type { ThemeId } from "./themes";
import { useTheme } from "./useTheme";

/**
 * Tema seçici: radyo grubu gibi davranır. Ok tuşları seçimi gezdirir ve hemen uygular;
 * odak yalnızca seçili seçenekte durur (tek Tab durağı).
 */
export default function ThemeSwitcher({ className }: { className?: string }) {
  const { theme, themes, setTheme } = useTheme();
  const groupRef = useRef<HTMLDivElement>(null);

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const keys: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    const step = keys[event.key];
    if (step === undefined) return;
    event.preventDefault();
    const index = themes.findIndex((option) => option.id === theme.id);
    const next = themes[(index + step + themes.length) % themes.length];
    setTheme(next.id);
    groupRef.current?.querySelector<HTMLButtonElement>(`[data-theme-id="${next.id}"]`)?.focus();
  }

  return (
    <div className={className}>
      <p id="theme-switcher-label" className="mb-2 px-1 text-xs font-medium text-graphite">
        Tema
      </p>
      <div
        ref={groupRef}
        role="radiogroup"
        aria-labelledby="theme-switcher-label"
        onKeyDown={move}
        className="flex flex-wrap gap-1.5"
      >
        {themes.map((option) => {
          const selected = option.id === theme.id;
          return (
            <ThemeChip
              key={option.id}
              id={option.id}
              label={option.label}
              description={option.description}
              ground={option.swatch.ground}
              accent={option.swatch.accent}
              selected={selected}
              onSelect={() => setTheme(option.id)}
            />
          );
        })}
      </div>
    </div>
  );
}

function ThemeChip({
  id,
  label,
  description,
  ground,
  accent,
  selected,
  onSelect,
}: {
  id: ThemeId;
  label: string;
  description: string;
  ground: string;
  accent: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      tabIndex={selected ? 0 : -1}
      data-theme-id={id}
      title={description}
      onClick={onSelect}
      className={cx(
        "inline-flex h-8 items-center gap-1.5 rounded-full border pr-3 pl-1.5 text-xs font-medium transition-colors",
        selected
          ? "border-accent-line bg-accent-soft text-accent"
          : "border-line bg-surface text-ink-2 hover:border-line-strong hover:text-ink",
      )}
    >
      <span
        aria-hidden
        className="relative inline-flex size-5 items-center justify-center overflow-hidden rounded-full border border-black/10"
        style={{ background: `linear-gradient(135deg, ${ground} 0 50%, ${accent} 50% 100%)` }}
      >
        {selected && <Check size={11} strokeWidth={3} className="relative text-white drop-shadow" />}
      </span>
      {label}
    </button>
  );
}
