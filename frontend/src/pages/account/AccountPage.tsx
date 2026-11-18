import { Trash2, UserX } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router";

import { useAuth } from "../../auth/useAuth";
import { authService } from "../../services/authService";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import { SectionHeader } from "../../ui/PageHeader";
import PageTitle from "../../ui/PageTitle";
import { useToast } from "../../ui/toast/context";
import { ROLE_LABELS } from "../../layouts/navigation";
import ThemeSwitcher from "../../theme/ThemeSwitcher";

type Pending = "data" | "account" | null;

/** Hesabım (ADR-4): araştırma kaydı tercihi, verilerimi sil, hesabımı sil. */
export default function AccountPage() {
  const { user, acceptPolicy, refresh } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Kutucuk tıklanınca hemen değişir; kayıt başarısız olursa eski hâline döner.
  const [research, setResearch] = useState(user?.researchLogging ?? false);

  if (!user) return null;

  async function toggleResearch(next: boolean) {
    setResearch(next);
    setSaving(true);
    try {
      await acceptPolicy(next);
      toast.show({
        tone: "success",
        title: next ? "Öğrenme kaydı açıldı" : "Öğrenme kaydı kapatıldı",
        description: next
          ? "Bundan sonra çözdüğün sorular öğrenme kaydına yazılır."
          : "Yeni denemeler kayda yazılmaz; eski kayıtların duruyor.",
      });
    } catch {
      setResearch(!next);
      toast.show({ tone: "danger", title: "Tercih kaydedilemedi", description: "Bağlantını kontrol edip tekrar dene." });
    } finally {
      setSaving(false);
    }
  }

  async function confirmDelete() {
    setDeleting(true);
    setError(null);
    try {
      if (pending === "data") {
        await authService.deleteMyData();
        setPending(null);
        await refresh();
        toast.show({
          tone: "success",
          title: "Verilerin silindi",
          description: "Sohbetlerin ve pratik cevapların (öğrenme kaydın) kalıcı olarak silindi.",
        });
      } else {
        await authService.deleteAccount();
        setPending(null);
        await refresh();
        navigate("/login", { replace: true });
      }
    } catch {
      setError("Silme işlemi tamamlanamadı. Bağlantını kontrol edip tekrar dene.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="page">
      <div className="max-w-3xl">
      <PageTitle title="Hesabım" description={`${user.name} · ${user.email} · ${ROLE_LABELS[user.role]}`} />

      <div className="flex flex-col gap-10">
        <section>
          <SectionHeader
            title="Öğrenme kaydı ve araştırma"
            description="Açıkken çözdüğün pratik soruları öğrenme kaydına yazılır ve takma adla, toplu olarak eğitmen analitiğine ve araştırmaya katılır."
          />
          <label className="flex cursor-pointer items-start gap-3 rounded-panel border border-line bg-surface px-4 py-3">
            <input
              type="checkbox"
              checked={research}
              disabled={saving}
              onChange={(event) => void toggleResearch(event.target.checked)}
              className="mt-1 size-4 accent-accent"
            />
            <span className="text-base text-ink">
              Öğrenme kaydımı tut ve kullanımımın araştırmada takma adla kullanılmasına izin ver.
              <span className="mt-1 block text-sm text-graphite">
                İsteğe bağlıdır; kapalıyken de platformu tam olarak kullanırsın. İstediğin zaman değiştirebilirsin.
              </span>
            </span>
          </label>
        </section>

        <section>
          <SectionHeader title="Görünüm" description="Renk teması bütün sayfalarda geçerlidir." />
          <ThemeSwitcher />
        </section>

        <section>
          <SectionHeader title="Verilerim" />
          <div className="flex flex-col divide-y divide-line rounded-panel border border-line bg-surface">
            <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center">
              <div className="flex-1">
                <p className="text-base font-medium text-ink">Verilerimi sil</p>
                <p className="text-sm text-graphite">
                  Bütün sohbetlerin ve pratik cevapların (öğrenme kaydın) silinir. Hesabın ve ders üyeliklerin kalır.
                </p>
              </div>
              <Button icon={Trash2} onClick={() => setPending("data")}>
                Verilerimi sil
              </Button>
            </div>
            <div className="flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-center">
              <div className="flex-1">
                <p className="text-base font-medium text-ink">Hesabımı sil</p>
                <p className="text-sm text-graphite">
                  Hesabın ve ona bağlı bütün kişisel verin kalıcı olarak silinir; oturumun kapanır.
                </p>
              </div>
              <Button variant="danger" icon={UserX} onClick={() => setPending("account")}>
                Hesabımı sil
              </Button>
            </div>
          </div>
        </section>
      </div>

      <Dialog
        open={pending !== null}
        onClose={() => {
          if (!deleting) {
            setPending(null);
            setError(null);
          }
        }}
        title={pending === "account" ? "Hesabın silinsin mi?" : "Verilerin silinsin mi?"}
        description="Bu işlem geri alınamaz."
        footer={
          <>
            {/* Geri alınamaz işlemde odak "Vazgeç"te başlar; Enter'a basmak silmez (#106). */}
            <Button variant="ghost" onClick={() => setPending(null)} disabled={deleting} data-autofocus>
              Vazgeç
            </Button>
            <Button variant="danger" onClick={() => void confirmDelete()} loading={deleting}>
              {pending === "account" ? "Hesabımı kalıcı olarak sil" : "Verilerimi kalıcı olarak sil"}
            </Button>
          </>
        }
      >
        <p className="text-base text-ink-2">
          {pending === "account"
            ? "Hesabın, sohbetlerin, pratik cevapların ve ders üyeliklerin silinir. Aynı e-postayla yeniden kayıt olabilirsin ama eski verilerin geri gelmez."
            : "Sohbetlerin ve pratik cevapların silinir; öğrenme kaydın boşalır. Hesabın ve derslerin kalır."}
        </p>
        {error && (
          <p role="alert" className="mt-3 text-base text-danger">
            {error}
          </p>
        )}
      </Dialog>
      </div>
    </div>
  );
}
