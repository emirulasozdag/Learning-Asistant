import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import type { Role } from "../services/authService";
import { homePath, useAuth } from "./useAuth";

/** Giriş yapılmamışsa login'e; yanlış roldeyse kendi ana sayfasına yönlendirir. */
export default function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (user.role !== role) return <Navigate to={homePath(user.role)} replace />;
  return children;
}
