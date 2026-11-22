import { Navigate, Outlet, useLocation } from "react-router";

import { afterLoginPath, useAuth } from "../auth/useAuth";
import AuthFrame from "./AuthFrame";

/** Giriş / kayıt: solda ürünü anlatan lacivert panel, sağda form. */
export default function AuthLayout() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  // Giriş/kayıt başarılı olunca kullanıcı burada yönlendirilir (istenen sayfa korunur).
  if (user) return <Navigate to={afterLoginPath(user.role, location.state)} replace />;

  return (
    <AuthFrame>
      <Outlet />
    </AuthFrame>
  );
}
