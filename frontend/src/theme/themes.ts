/**
 * Arayüz temaları. Açık tema ("Dipnot") uygulamanın taban paletidir (index.css `@theme`); koyu tema
 * ("Gece") themes.css'te `html[data-theme="gece"]` altında üzerine yazar. Burada yalnızca
 * seçicinin gösterdiği bilgi durur.
 */
export type ThemeId = "dipnot" | "gece";

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
    id: "dipnot",
    label: "Açık",
    scheme: "light",
    swatch: { ground: "#f6f7f9", accent: "#102e6e" },
    description: "Açık zemin, üniversite lacivertı.",
  },
  {
    id: "gece",
    label: "Koyu",
    scheme: "dark",
    swatch: { ground: "#0e1626", accent: "#8fb0ff" },
    description: "Koyu zemin; gece çalışırken gözü yormaz.",
  },
];

export const DEFAULT_THEME: ThemeId = "dipnot";

/** Önceki sürümün tema kimlikleri: koyu temayı seçen koyuda, diğerleri açıkta kalır. */
const LEGACY_THEMES: Record<string, ThemeId> = {
  "pastel-koyu": "gece",
  "pastel-acik": "dipnot",
  "bordo-pastel": "dipnot",
  sade: "dipnot",
  kagit: "dipnot",
};

export function findTheme(id: string | null | undefined): ThemeOption | undefined {
  const resolved = id && id in LEGACY_THEMES ? LEGACY_THEMES[id] : id;
  return THEMES.find((theme) => theme.id === resolved);
}
