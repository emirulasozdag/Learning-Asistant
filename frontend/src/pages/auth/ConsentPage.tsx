import { ShieldCheck } from "lucide-react";
import { useState } from "react";

import { userMessage } from "../../api/errors";
import { useAuth } from "../../auth/useAuth";
import AuthFrame from "../../layouts/AuthFrame";
import { PRIVACY_POLICY_VERSION } from "../../services/authService";
import Button from "../../ui/Button";
import CheckboxCard from "../../ui/CheckboxCard";
import ErrorText from "../../ui/ErrorText";
import { usePageTitle } from "../../ui/usePageTitle";

/**
 * Aydınlatma metni (ADR-4): ilk girişte gösterilir; kabul edilmeden soru sorulamaz. Araştırma kaydı
 * ayrı bir seçimdir ve varsayılan kapalıdır. Metin değişirse PRIVACY_POLICY_VERSION artırılır.
 */
export default function ConsentPage() {
  const { user, acceptPolicy, logout } = useAuth();
  const [research, setResearch] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  usePageTitle("Aydınlatma metni");

  async function accept() {
    setSaving(true);
    setError(null);
    try {
      await acceptPolicy(research);
    } catch (reason) {
      setError(userMessage(reason, "Onayın kaydedilemedi. Tekrar dene."));
      setSaving(false);
    }
  }

  return (
    <AuthFrame wide>
      <div className="flex items-center gap-3">
        <ShieldCheck size={24} aria-hidden className="text-accent" />
        <h1 className="text-2xl font-bold tracking-tight text-ink">Aydınlatma metni</h1>
      </div>
      <p className="mt-2 text-base text-graphite">
        {user?.name ? `${user.name}, ` : ""}devam etmeden önce verilerinin nasıl kullanıldığını oku.
      </p>

      <div className="mt-6 flex flex-col gap-4 font-serif text-md leading-relaxed text-ink">
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

      <CheckboxCard
        className="mt-6"
        checked={research}
        onChange={setResearch}
        label="İsteğe bağlı: araştırmaya katkı"
        description="Kullanımımın, sistemi geliştirmek için yapılan araştırmada takma adla kullanılmasına izin veriyorum. İşaretlemesen de platformu tam olarak kullanırsın."
      />

      {error && <ErrorText className="mt-4">{error}</ErrorText>}

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <Button variant="primary" size="lg" loading={saving} onClick={() => void accept()}>
          Okudum, kabul ediyorum
        </Button>
        <Button variant="ghost" onClick={() => void logout()} disabled={saving}>
          Çıkış yap
        </Button>
      </div>
      <p className="mt-4 text-xs text-faint">Metin sürümü {PRIVACY_POLICY_VERSION}</p>
    </AuthFrame>
  );
}
