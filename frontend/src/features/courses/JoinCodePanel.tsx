import { Copy, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";

import { userMessage } from "../../api/errors";
import type { JoinCode } from "../../api/types";
import { courseService } from "../../services/courseService";
import Button from "../../ui/Button";
import InlineError from "../../ui/InlineError";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { formatDate } from "../../text";
import { useToast } from "../../ui/toast/context";

/** Eğitmen: öğrencilerin derse katılması için kod (ADR-2). Yenilenince eski kod geçersiz olur. */
export default function JoinCodePanel({ courseId }: { courseId: number }) {
  const toast = useToast();
  const [joinCode, setJoinCode] = useState<JoinCode | null>(null);
  const [failed, setFailed] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [attempt, setAttempt] = useState(0);

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
  }, [courseId, attempt]);

  function retry() {
    setFailed(false);
    setJoinCode(null);
    setAttempt((value) => value + 1);
  }

  async function rotate() {
    setRotating(true);
    try {
      setJoinCode(await courseService.rotateJoinCode(courseId));
      toast.show({ tone: "success", title: "Yeni katılım kodu oluşturuldu", description: "Eski kod artık çalışmaz." });
    } catch (reason) {
      toast.show({ tone: "danger", title: "Kod yenilenemedi", description: userMessage(reason, "Bağlantını kontrol edip tekrar dene.") });
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
        level={2}
        title="Katılım kodu"
        description="Öğrenciler bu kodla derse katılır. Kod sızdıysa yenile; var olan öğrenciler derste kalır."
      />
      {failed ? (
        <InlineError message="Katılım koduna şu an ulaşılamıyor." onRetry={retry} />
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
              Geçerlilik: {formatDate(joinCode.expires_at)}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
