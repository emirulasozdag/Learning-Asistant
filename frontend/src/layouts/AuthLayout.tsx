import { Library, Quote, ShieldCheck } from "lucide-react";
import { Navigate, Outlet } from "react-router";

import { homePath, useAuth } from "../auth/useAuth";
import Logo from "../ui/Logo";

const PROOF_POINTS = [
  {
    icon: Quote,
    title: "Her cevap kaynağına bağlı",
    text: "Öğrenci, bilginin hangi notun hangi sayfasından geldiğini tek tıkla görür.",
  },
  {
    icon: ShieldCheck,
    title: "Yalnızca dersin materyali",
    text: "Materyalde olmayan bir şeye cevap uydurmaz; bunu açıkça söyler.",
  },
  {
    icon: Library,
    title: "Bilgi tabanı eğitmende",
    text: "Notlar, slaytlar ve geçmiş sınavlar dersin kendi bilgi tabanına dönüşür.",
  },
];

/** Giriş / kayıt: solda ürünün değer önerisi, sağda form. */
export default function AuthLayout() {
  const { user } = useAuth();
  if (user) return <Navigate to={homePath(user.role)} replace />;

  return (
    <div className="grid min-h-dvh bg-surface lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <section className="relative hidden flex-col justify-between border-r border-line bg-canvas px-12 py-10 lg:flex xl:px-16">
        <Logo />

        <div className="max-w-xl py-12">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink">
            Dersin. Materyalin.
            <br />
            Yapay zekâ asistanın.
          </h1>
          <p className="mt-4 max-w-md text-md text-graphite">
            Ders notlarından, slaytlardan ve geçmiş sınavlardan öğrenen; her cevabını kaynağıyla
            gösteren bir çalışma asistanı.
          </p>

          <ProductGlimpse />

          <ul className="mt-10 grid gap-5 xl:grid-cols-3">
            {PROOF_POINTS.map(({ icon: Icon, title, text }) => (
              <li key={title}>
                <Icon size={16} aria-hidden className="text-accent" />
                <p className="mt-2 text-base font-medium text-ink">{title}</p>
                <p className="mt-1 text-sm text-graphite">{text}</p>
              </li>
            ))}
          </ul>
        </div>

        <p className="text-sm text-faint">Pilot ders: Veri Yapıları ve Algoritmalar</p>
      </section>

      <section className="flex flex-col px-6 py-8 sm:px-10">
        <Logo className="lg:hidden" />
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-sm">
            <Outlet />
          </div>
        </div>
      </section>
    </div>
  );
}

/** Ürünün kendisinden küçük bir an: soru, kaynaklı cevap, işaretli kaynak. */
function ProductGlimpse() {
  return (
    <figure
      aria-label="Örnek: kaynaklı bir AI Tutor cevabı"
      className="mt-10 max-w-lg rounded-panel border border-line bg-surface p-5 shadow-page"
    >
      <p className="text-sm text-graphite">BLM2512 Veri Yapıları ve Algoritmalar</p>
      <p className="mt-3 border-l-2 border-accent pl-3 text-base font-medium text-ink">
        Binary search neden sıralı bir dizi gerektirir?
      </p>
      <p className="mt-3 text-base leading-relaxed text-ink-2">
        Her adımda ortadaki eleman hedefle karşılaştırılır. Dizi sıralı olduğu için hedef küçükse
        sağdaki tüm elemanlar da hedeften büyüktür ve güvenle elenebilir{" "}
        <span className="inline-flex min-w-5 justify-center rounded-sm bg-marker px-1 text-xs font-semibold text-ink">
          1
        </span>
        <span>.</span>
      </p>
      <div className="mt-4 flex items-center gap-3 rounded-control border border-line bg-canvas px-3 py-2">
        <span className="flex size-7 items-center justify-center rounded bg-surface text-[10px] font-semibold text-danger ring-1 ring-line">
          PDF
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">Ders Notları 05.pdf</p>
          <p className="truncate font-serif text-sm text-graphite">
            “…dizi sıralı olduğundan hedef orta elemandan küçükse…”
          </p>
        </div>
        <span className="ml-auto shrink-0 text-sm text-graphite">Sayfa 12</span>
      </div>
    </figure>
  );
}
