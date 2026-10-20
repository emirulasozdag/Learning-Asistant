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

/**
 * Girişten sonra gidilecek adres: korumalı sayfadan girişe yönlendirildiyse (`state.from`) ve o sayfa
 * bu rolün alanındaysa oraya, yoksa rolün ana sayfasına.
 */
export function afterLoginPath(role: "student" | "instructor", state: unknown): string {
  const from = (state as { from?: string } | null)?.from;
  return from?.startsWith(homePath(role)) ? from : homePath(role);
}
