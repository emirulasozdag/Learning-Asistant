import { Compass } from "lucide-react";
import { Link, Navigate } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import AuthFrame from "../layouts/AuthFrame";
import { buttonClasses } from "../ui/buttonStyles";
import EmptyState from "../ui/EmptyState";
import { usePageTitle } from "../ui/usePageTitle";

/** "/" — rolün ana sayfasına ya da girişe yönlendirir. */
export function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? homePath(user.role) : "/login"} replace />;
}

export function NotFound() {
  usePageTitle("Sayfa bulunamadı");
  return (
    <AuthFrame>
      <EmptyState
        level={1}
        icon={Compass}
        title="Sayfa bulunamadı"
        description="Adres değişmiş ya da hiç var olmamış olabilir."
        action={
          <Link to="/" className={buttonClasses("primary")}>
            Ana sayfaya dön
          </Link>
        }
      />
    </AuthFrame>
  );
}
