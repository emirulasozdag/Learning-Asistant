import { Compass } from "lucide-react";
import { Link, Navigate } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import { buttonClasses } from "../ui/buttonStyles";
import EmptyState from "../ui/EmptyState";

/** "/" — rolün ana sayfasına ya da girişe yönlendirir. */
export function RootRedirect() {
  const { user } = useAuth();
  return <Navigate to={user ? homePath(user.role) : "/login"} replace />;
}

export function NotFound() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas">
      <EmptyState
        icon={Compass}
        title="Sayfa bulunamadı"
        description="Adres değişmiş ya da hiç var olmamış olabilir."
        action={
          <Link to="/" className={buttonClasses("secondary")}>
            Ana sayfaya dön
          </Link>
        }
      />
    </div>
  );
}
