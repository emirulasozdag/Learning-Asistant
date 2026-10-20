import { useContext } from "react";

import { StudioContext, type StudioContextValue } from "./context";

export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (!context) throw new Error("useStudio, StudioShell içinde kullanılmalı");
  return context;
}
