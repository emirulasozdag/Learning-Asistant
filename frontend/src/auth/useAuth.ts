import { useContext } from "react";

import { AuthContext, type AuthContextValue } from "./context";

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth, AuthProvider içinde kullanılmalı");
  return context;
}

/** Rolün ana sayfası: girişten sonra ve "/" adresinde buraya gidilir. */
export function homePath(role: "student" | "instructor"): string {
  return role === "instructor" ? "/instructor" : "/student";
}
