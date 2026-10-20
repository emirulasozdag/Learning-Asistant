import { ServerOff } from "lucide-react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import ConsentPage from "../pages/auth/ConsentPage";
import type { Role } from "../services/authService";
import Button from "../ui/Button";
import EmptyState from "../ui/EmptyState";
import { homePath, useAuth } from "./useAuth";

/**
 * Korumalı alan: oturum çözülene kadar bekler; giriş yoksa login'e, yanlış roldeyse kendi ana
 * sayfasına yönlendirir; aydınlatma metni kabul edilmemişse önce onu gösterir (ADR-4).
 */
export default function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, loading, failed, refresh } = useAuth();
  const location = useLocation();
  if (loading) return null;
  if (!user && failed) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-canvas">
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Sunucuya ulaşılamıyor"
          description="Oturum bilgisi alınamadı. Bağlantını kontrol edip tekrar dene."
          action={<Button onClick={() => void refresh()}>Tekrar dene</Button>}
        />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (user.role !== role) return <Navigate to={homePath(user.role)} replace />;
  if (!user.consented) return <ConsentPage />;
  return children;
}
