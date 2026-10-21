import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import { useAuth } from "../../auth/useAuth";
import { PRIVACY_POLICY_VERSION } from "../../services/authService";
import Button from "../../ui/Button";
import Logo from "../../ui/Logo";

/**
 * Aydınlatma metni (ADR-4): ilk girişte gösterilir; kabul edilmeden soru sorulamaz. Araştırma kaydı
 * ayrı bir seçimdir ve varsayılan kapalıdır. Metin değişirse PRIVACY_POLICY_VERSION artırılır.
 */
export default function ConsentPage() {
  const { user, acceptPolicy, logout } = useAuth();
  const [research, setResearch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function accept() {
    setSaving(true);
    setError(null);
    try {
      await acceptPolicy(research);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <header className="flex h-[4.5rem] shrink-0 items-center border-b border-line bg-surface px-5 sm:px-8">
        <Logo onDark />
      </header>
      <main className="mx-auto w-full max-w-2xl flex-1 px-5 py-10 sm:px-8">
        <section className="rounded-panel border border-line bg-surface px-6 py-8 sm:px-10">
          <div className="flex items-center gap-3">
            <ShieldCheck size={22} aria-hidden className="text-accent" />
            <h1 className="text-2xl font-semibold tracking-tight text-ink">Aydınlatma metni</h1>
          </div>
          <p className="mt-2 text-base text-graphite">
            {user?.name ? `${user.name}, ` : ""}devam etmeden önce verilerinin nasıl kullanıldığını oku.
          </p>

          <div className="mt-6 flex flex-col gap-4 text-md leading-relaxed text-ink">
            <p>
              <strong>Ne saklanır:</strong> Sorduğun sorular ve aldığın cevaplar hesabına bağlı olarak saklanır.
              Takip sorularının anlaşılması ve sohbet geçmişin için gereklidir. Saklama süresi dönem sonuna göre
              belirlenecektir.
            </p>
            <p>
              <strong>Yapay zekâ servisi:</strong> Cevap üretmek için sorun, dersin ilgili bölümleri ve son birkaç
              mesaj harici bir yapay zekâ servisine gönderilir. Adın, e-postan ve kimlik bilgilerin gönderilmez.
            </p>
            <p>
              <strong>Eğitmen görünümü:</strong> Eğitmen dersin soru-cevap etkinliğini toplu olarak görür; kişi bazlı
              gösterim yoktur.
            </p>
            <p>
              <strong>Hakların:</strong> Sohbetlerinin ya da hesabının silinmesini isteyebilirsin.
            </p>
          </div>

          <label className="mt-6 flex cursor-pointer items-start gap-3 rounded-panel border border-line bg-canvas px-4 py-3">
            <input
              type="checkbox"
              checked={research}
              onChange={(event) => setResearch(event.target.checked)}
              className="mt-1 size-4 accent-accent"
            />
            <span className="text-base text-ink">
              <span className="font-medium">İsteğe bağlı:</span> Kullanımımın, sistemi geliştirmek için yapılan
              araştırmada takma adla kullanılmasına izin veriyorum. İşaretlemesen de platformu tam olarak kullanırsın.
            </span>
          </label>

          {error && (
            <p role="alert" className="mt-4 text-base text-danger">
              {error}
            </p>
          )}

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" loading={saving} onClick={() => void accept()}>
              Okudum, kabul ediyorum
            </Button>
            <Button variant="ghost" onClick={() => void logout()} disabled={saving}>
              Çıkış yap
            </Button>
          </div>
          <p className="mt-4 text-sm text-graphite">Metin sürümü: {PRIVACY_POLICY_VERSION}</p>
        </section>
      </main>
    </div>
  );
}
