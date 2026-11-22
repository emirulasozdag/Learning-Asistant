import type { ReactNode } from "react";

import Logo from "../ui/Logo";
import UniversityLogo from "../ui/UniversityLogo";

/**
 * Giriş, kayıt, aydınlatma metni ve "sayfa bulunamadı" ekranlarının ortak çerçevesi.
 *
 * Solda lacivert panel ürünü kendi biçimiyle anlatır: bir cümle ve altındaki dipnot (her cevabın
 * kaynağına bağlanması). Dar ekranda panel üstte kısa bir şeride dönüşür. Sağda içerik.
 */
export default function AuthFrame({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="flex min-h-dvh flex-col bg-canvas lg:flex-row">
      <aside className="flex shrink-0 flex-col bg-chrome px-6 py-6 text-chrome-ink sm:px-10 lg:sticky lg:top-0 lg:h-dvh lg:w-[min(46%,40rem)] lg:overflow-y-auto lg:px-12 lg:py-10">
        <div className="flex items-center gap-4">
          <UniversityLogo />
          <span aria-hidden className="h-7 w-px bg-white/20" />
          <Logo inverse />
        </div>

        <div className="mt-8 lg:mt-auto">
          <p className="max-w-xl text-3xl font-semibold tracking-tight text-balance lg:text-4xl">
            Her cevabın bir dipnotu var
            <span aria-hidden className="footnote-mark ml-1.5">
              1
            </span>
          </p>
          <p className="mt-4 max-w-lg text-md text-chrome-muted">
            Ders notlarına, slaytlara ve ders videolarına dayanan çalışma asistanı. Cevaptaki her cümle,
            dayandığı sayfaya ya da videodaki ana bağlanır.
          </p>
          <ul className="mt-8 hidden max-w-lg flex-col gap-3 text-base text-chrome-muted lg:flex">
            <li>
              <span className="font-semibold text-chrome-ink">Yalnızca ders materyali.</span> Materyalde dayanak
              yoksa tahmin etmez, bunu açıkça söyler.
            </li>
            <li>
              <span className="font-semibold text-chrome-ink">Pratik ve geri bildirim.</span> Konunu seç, soruları
              çöz, eksiklerin üzerine yeni soru al.
            </li>
            <li>
              <span className="font-semibold text-chrome-ink">Eğitmen yönetiminde.</span> Materyali eğitmen yükler;
              öğrencilerin zorlandığı konuları görür.
            </li>
          </ul>
        </div>

        <p className="mt-6 hidden max-w-lg border-t border-white/15 pt-4 text-sm text-chrome-muted lg:mt-auto lg:block">
          <span className="footnote-mark mr-2 align-baseline">1</span>
          Dipnota dokununca cevabın dayandığı ders notu sayfası ya da video anı açılır.
        </p>
      </aside>

      <main className="flex flex-1 items-start justify-center px-5 py-10 sm:px-8 lg:items-center lg:py-16">
        <div className={wide ? "w-full max-w-2xl" : "w-full max-w-md"}>{children}</div>
      </main>
    </div>
  );
}
