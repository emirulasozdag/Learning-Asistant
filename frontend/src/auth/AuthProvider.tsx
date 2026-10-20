import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { setUnauthorizedHandler } from "../api/client";
import { authService, type RegisterInput, type Role, type User } from "../services/authService";
import { AuthContext } from "./context";

export default function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setUser(await authService.currentUser());
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    authService
      .currentUser()
      .then((current) => {
        if (!cancelled) setUser(current);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    // Oturum süresi dolarsa (herhangi bir istekte 401) kullanıcı çıkış yapmış sayılır;
    // korumalı sayfalar girişe yönlendirir.
    setUnauthorizedHandler(() => setUser(null));
    return () => {
      cancelled = true;
      setUnauthorizedHandler(null);
    };
  }, []);

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

  const demoLogin = useCallback(async (role: Role) => {
    const next = await authService.demoLogin(role);
    setUser(next);
    return next;
  }, []);

  const acceptPolicy = useCallback(
    async (researchLogging: boolean) => {
      await authService.acceptPolicy(researchLogging);
      await refresh();
    },
    [refresh],
  );

  const logout = useCallback(async () => {
    await authService.logout();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, failed, login, register, demoLogin, acceptPolicy, refresh, logout }),
    [user, loading, failed, login, register, demoLogin, acceptPolicy, refresh, logout],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}
