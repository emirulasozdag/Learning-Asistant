import { useCallback, useMemo, useState, type ReactNode } from "react";

import { authService, type RegisterInput, type User } from "../services/authService";
import { AuthContext } from "./context";

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => authService.currentUser());

  const login = useCallback(async (email: string, password: string) => {
    const next = await authService.login(email, password);
    setUser(next);
    return next;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const next = await authService.register(input);
    setUser(next);
    return next;
  }, []);

  const loginAs = useCallback(async (demo: User) => {
    const next = await authService.loginAs(demo);
    setUser(next);
    return next;
  }, []);

  const logout = useCallback(() => {
    authService.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, login, register, loginAs, logout }),
    [user, login, register, loginAs, logout],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}
