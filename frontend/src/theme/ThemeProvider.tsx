import { useCallback, useLayoutEffect, useMemo, useState, type ReactNode } from "react";

import { ThemeContext } from "./context";
import { DEFAULT_THEME, THEMES, findTheme, type ThemeId } from "./themes";

const STORAGE_KEY = "la.theme";

function readStoredTheme(): ThemeId {
  try {
    return findTheme(localStorage.getItem(STORAGE_KEY))?.id ?? DEFAULT_THEME;
  } catch {
    return DEFAULT_THEME;
  }
}

/**
 * Seçili temayı `<html>` öğesine yazar (`data-theme`, `data-scheme`, `color-scheme`) ve tarayıcıda
 * saklar. Renkler CSS değişkenleri olduğu için bütün uygulama yeniden çizilmeden temaya uyar.
 */
export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeId] = useState<ThemeId>(readStoredTheme);
  const theme = findTheme(themeId) ?? THEMES[0];

  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme.id;
    root.dataset.scheme = theme.scheme;
    root.style.colorScheme = theme.scheme;
  }, [theme]);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeId(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      // tercih kaydedilemedi; bu oturumda yine de uygulanır
    }
  }, []);

  const value = useMemo(() => ({ theme, themes: THEMES, setTheme }), [theme, setTheme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
