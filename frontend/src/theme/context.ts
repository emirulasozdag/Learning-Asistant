import { createContext } from "react";

import type { ThemeId, ThemeOption } from "./themes";

export interface ThemeContextValue {
  theme: ThemeOption;
  themes: readonly ThemeOption[];
  setTheme: (id: ThemeId) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);
