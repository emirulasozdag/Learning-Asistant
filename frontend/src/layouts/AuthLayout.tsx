import { Navigate, Outlet } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import InfoPanel from "../ui/InfoPanel";
import Logo from "../ui/Logo";

/** Giriş / kayıt: kurumsal üst bar, mavi şerit, solda form, sağda platform hakkında. */
export default function AuthLayout() {
  const { user } = useAuth();
  if (user) return <Navigate to={homePath(user.role)} replace />;

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="flex h-[4.5rem] shrink-0 items-center bg-nav px-5 sm:px-8">
        <Logo onDark />
      </header>

      <div className="bg-banner text-white">
        <div className="mx-auto max-w-[72rem] px-5 py-9 sm:px-8 lg:px-10 lg:py-12">
          <p className="text-base font-semibold">Üniversite öğrenme platformu</p>
          <h1 className="mt-3 max-w-3xl text-[2.25rem] leading-tight font-normal tracking-tight text-balance sm:text-[2.75rem]">
            Ders materyaline dayanan, kaynağını gösteren yapay zekâ asistanı
          </h1>
        </div>
      </div>

      <main className="mx-auto grid w-full max-w-[72rem] flex-1 gap-8 px-5 py-10 sm:px-8 lg:grid-cols-[minmax(0,1fr)_22rem] lg:px-10">
        <section className="self-start rounded-panel border border-line bg-surface px-6 py-8 sm:px-10">
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

      <footer className="border-t border-line bg-surface">
        <p className="mx-auto max-w-[72rem] px-5 py-5 text-sm text-graphite sm:px-8 lg:px-10">
          Pilot ders: Veri Yapıları ve Algoritmalar
        </p>
      </footer>
    </div>
  );
}
