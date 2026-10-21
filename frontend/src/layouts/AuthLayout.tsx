import { Navigate, Outlet, useLocation } from "react-router";

import { afterLoginPath, useAuth } from "../auth/useAuth";
import InfoPanel from "../ui/InfoPanel";
import Logo from "../ui/Logo";
import UniversityLogo from "../ui/UniversityLogo";

/** Giriş / kayıt: kurum ve ürün başlığı, açık giriş bölümü, solda form, sağda platform hakkında. */
export default function AuthLayout() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  // Giriş/kayıt başarılı olunca kullanıcı burada yönlendirilir (istenen sayfa korunur).
  if (user) return <Navigate to={afterLoginPath(user.role, location.state)} replace />;

  return (
    <div className="studio-grid flex min-h-dvh flex-col">
      <header className="flex h-[4.5rem] shrink-0 items-center gap-4 border-b border-line bg-surface/85 px-5 backdrop-blur sm:px-8">
        <UniversityLogo />
        <Logo />
      </header>

      <div>
        <div className="mx-auto max-w-[72rem] px-5 pt-10 pb-2 sm:px-8 lg:px-10 lg:pt-14">
          <p className="font-mono text-xs text-graphite">Üniversite öğrenme platformu</p>
          <h1 className="mt-3 max-w-3xl text-[2.25rem] leading-[1.08] font-semibold tracking-tight text-balance text-ink sm:text-[2.875rem]">
            Ders materyaline dayanan, kaynağını gösteren yapay zekâ asistanı
          </h1>
        </div>
      </div>

      <main className="mx-auto grid w-full max-w-[72rem] flex-1 gap-8 px-5 py-10 sm:px-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:px-10">
        <section className="self-start rounded-panel border border-line bg-surface px-6 py-8 shadow-card sm:px-10">
          <div className="max-w-md">
            <Outlet />
          </div>
        </section>
        <InfoPanel
          title="Bu platform hakkında"
          className="self-start"
          sections={[
            {
              label: "Kaynağa bağlı cevaplar",
              content: "Her cevap, dayandığı ders notunun sayfasına tek tıkla açılır.",
            },
            {
              label: "Yalnızca ders materyali",
              content: "Materyalde yeterli dayanak yoksa cevap üretmek yerine bunu açıkça söyler.",
            },
            {
              label: "Eğitmen yönetiminde",
              content:
                "Notlar, slaytlar ve geçmiş sınavlar dersin bilgi tabanı olur; eğitmen öğrenci sorularını izler.",
            },
          ]}
        />
      </main>

      <footer className="border-t border-line bg-surface/85">
        <p className="mx-auto max-w-[72rem] px-5 py-5 text-sm text-graphite sm:px-8 lg:px-10">
          Pilot ders: Veri Yapıları ve Algoritmalar
        </p>
      </footer>
    </div>
  );
}
