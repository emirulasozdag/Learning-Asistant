import { Copy, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import type { JoinCode } from "../../api/types";
import { courseService } from "../../services/courseService";
import Button from "../../ui/Button";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { useToast } from "../../ui/toast/context";

/** Eğitmen: öğrencilerin derse katılması için kod (ADR-2). Yenilenince eski kod geçersiz olur. */
export default function JoinCodePanel({ courseId }: { courseId: number }) {
  const toast = useToast();
  const [joinCode, setJoinCode] = useState<JoinCode | null>(null);
  const [failed, setFailed] = useState(false);
  const [rotating, setRotating] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    courseService
      .joinCode(courseId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setJoinCode(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [courseId]);

  async function rotate() {
    setRotating(true);
    try {
      setJoinCode(await courseService.rotateJoinCode(courseId));
      toast.show({ tone: "success", title: "Yeni katılım kodu oluşturuldu", description: "Eski kod artık çalışmaz." });
    } catch (reason) {
      toast.show({ tone: "danger", title: "Kod yenilenemedi", description: reason instanceof Error ? reason.message : undefined });
    } finally {
      setRotating(false);
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      toast.show({ tone: "success", title: "Katılım kodu kopyalandı" });
    } catch {
      toast.show({ tone: "neutral", title: "Kopyalanamadı", description: "Kodu elle seçip kopyala." });
    }
  }

  return (
    <section>
      <PageTitle
        title="Katılım kodu"
        description="Öğrenciler bu kodla derse katılır. Kod sızdıysa yenile; var olan öğrenciler derste kalır."
      />
      {failed ? (
        <p className="text-md text-danger">Katılım koduna şu an ulaşılamıyor.</p>
      ) : joinCode === null ? (
        <SkeletonRows rows={1} />
      ) : (
        <div className="flex flex-wrap items-center gap-4">
          <code className="rounded-control border border-line bg-surface px-4 py-2 font-mono text-xl font-semibold tracking-[0.2em] text-ink">
            {joinCode.code}
          </code>
          <Button icon={Copy} onClick={() => void copy(joinCode.code)}>
            Kopyala
          </Button>
          <Button icon={RefreshCw} variant="ghost" loading={rotating} onClick={() => void rotate()}>
            Yenile
          </Button>
          {joinCode.expires_at && (
            <p className="w-full text-sm text-graphite">
              Geçerlilik: {new Date(joinCode.expires_at).toLocaleDateString("tr-TR", { day: "numeric", month: "long", year: "numeric" })}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
