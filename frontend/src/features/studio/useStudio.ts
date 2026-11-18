import { useContext } from "react";

import { StudioContext, type StudioContextValue } from "./context";

export function useStudio(): StudioContextValue {
  const context = useContext(StudioContext);
  if (!context) throw new Error("useStudio, StudioProvider (CourseShell) içinde kullanılmalı");
  return context;
}
