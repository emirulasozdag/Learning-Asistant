import { useContext } from "react";

import { ThemeContext, type ThemeContextValue } from "./context";

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme, ThemeProvider içinde kullanılmalı");
  return context;
}
