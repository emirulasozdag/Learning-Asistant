/**
 * Arayüz temaları. Renk değerleri `themes.css` içinde, `html[data-theme]` altında tanımlıdır;
 * burada yalnızca seçicinin gösterdiği bilgi durur. "Sade" uygulamanın taban paletidir
 * (index.css `@theme`), üzerine bir şey yazmaz.
 */
export type ThemeId = "pastel-acik" | "pastel-koyu" | "bordo-pastel" | "sade" | "kagit";

export type ColorScheme = "light" | "dark";

export interface ThemeOption {
  id: ThemeId;
  label: string;
  /** Tarayıcıya bildirilen renk düzeni: kaydırma çubukları ve form denetimleri buna uyar. */
  scheme: ColorScheme;
  /** Seçicideki küçük örnek: zemin ve vurgu rengi. */
  swatch: { ground: string; accent: string };
  description: string;
}

export const THEMES: readonly ThemeOption[] = [
  {
    id: "pastel-acik",
    label: "Pastel açık",
    scheme: "light",
    swatch: { ground: "#f6f5fb", accent: "#5b57c9" },
    description: "Açık lavanta zemin, sakin mor vurgu.",
  },
  {
    id: "pastel-koyu",
    label: "Pastel koyu",
    scheme: "dark",
    swatch: { ground: "#1f1e27", accent: "#e3a3b8" },
    description: "Koyu zemin, gözü yormayan pastel gül vurgu.",
  },
  {
    id: "bordo-pastel",
    label: "Bordo pastel",
    scheme: "light",
    swatch: { ground: "#f4f1ec", accent: "#9a1f36" },
    description: "Sıcak kırık beyaz zemin, akademik bordo vurgu.",
  },
  {
    id: "sade",
    label: "Sade",
    scheme: "light",
    swatch: { ground: "#f3f4f8", accent: "#9a1f36" },
    description: "Soğuk nötr zemin, kurumsal görünüm.",
  },
  {
    id: "kagit",
    label: "Kâğıt",
    scheme: "light",
    swatch: { ground: "#f7f6f1", accent: "#2b5a8a" },
    description: "Defter kâğıdı zemin, mürekkep mavisi vurgu.",
  },
];

export const DEFAULT_THEME: ThemeId = "bordo-pastel";

export function findTheme(id: string | null | undefined): ThemeOption | undefined {
  return THEMES.find((theme) => theme.id === id);
}
