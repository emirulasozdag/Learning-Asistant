import { CircleCheck, ListChecks, ServerOff, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";

import type { MistakeSummary, PracticeItemReview } from "../../api/types";
import ReviewDialog, { type ReviewTarget } from "../../features/instructor/ReviewDialog";
import { SourceDrawer } from "../../features/tutor/SourceViewer";
import { citationLabel } from "../../labels";
import { instructorService } from "../../services/instructorService";
import { formatRelative } from "../../text";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import { SectionHeader } from "../../ui/PageHeader";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import { useToast } from "../../ui/toast/context";

const TYPE_LABELS: Record<PracticeItemReview["type"], string> = {
  mcq: "Çoktan seçmeli",
  short_answer: "Kısa cevap",
  code_tracing: "Kod izleme",
};

const DIFFICULTY_LABELS: Record<PracticeItemReview["difficulty"], string> = {
  easy: "Kolay",
  medium: "Orta",
  hard: "Zor",
};

/**
 * Eğitmen incelemesi (#20, #22): sınıfın sık hataları (anonim) ve öğrencilere sunulan pratik
 * soruları; her soru cevap anahtarıyla görünür, onaylanır ya da düzeltilir.
 */
export default function CourseReviewPage() {
  const courseId = Number(useParams().courseId);
  const [sourceId, setSourceId] = useState<string | null>(null);
  return (
    <div>
      <PageTitle
        title="İnceleme ve sık hatalar"
        description="Öğrencilerin pratikte en çok zorlandığı kavramlar ve sistemin ürettiği sorular. Öğrenci kimliği gösterilmez."
      />
      <div className="flex flex-col gap-12">
        <MistakesSection courseId={courseId} onOpenSource={setSourceId} />
        <PracticeItemsSection courseId={courseId} onOpenSource={setSourceId} />
      </div>
      {sourceId && <SourceDrawer sourceId={sourceId} onClose={() => setSourceId(null)} />}
    </div>
  );
}

function useLoad<T>(load: (signal: AbortSignal) => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
    // `load` her çizimde yeniden oluşur; yalnızca bağımlılıklar değişince yüklenir.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, attempt]);
  return {
    data,
    setData,
    failed,
    reload: () => {
      setFailed(false);
      setData(null);
      setAttempt((value) => value + 1);
    },
  };
}

function LoadFailed({ what, onRetry }: { what: string; onRetry: () => void }) {
  return (
    <EmptyState
      icon={ServerOff}
      tone="danger"
      title={`${what} yüklenemedi`}
      description="Şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
      action={<Button onClick={onRetry}>Tekrar dene</Button>}
    />
  );
}

function MistakesSection({ courseId, onOpenSource }: { courseId: number; onOpenSource: (id: string) => void }) {
  const { data, failed, reload } = useLoad((signal) => instructorService.mistakes(courseId, signal), [courseId]);
  return (
    <section>
      <SectionHeader
        title="Sık hatalar"
        description="Araştırma kaydını açan öğrencilerin pratik cevaplarından, toplu hesaplanır. En az üç farklı öğrencide görülen hatalar listelenir."
      />
      {failed ? (
        <LoadFailed what="Sık hatalar" onRetry={reload} />
      ) : !data ? (
        <SkeletonRows rows={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="Henüz yeterli veri yok"
          description="Bir hatanın görünmesi için en az üç öğrencinin aynı kavramda zorlanması gerekir; böylece kimse tek başına ayırt edilemez."
        />
      ) : (
        <MistakeTable mistakes={data} onOpenSource={onOpenSource} />
      )}
    </section>
  );
}

function MistakeTable({ mistakes, onOpenSource }: { mistakes: MistakeSummary[]; onOpenSource: (id: string) => void }) {
  return (
    <ol className="flex flex-col divide-y divide-line border-y border-line">
      {mistakes.map((mistake, index) => (
        <li key={`${mistake.concept}-${mistake.error_type}`} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center">
          <span className="w-5 text-sm font-semibold text-faint tabular-nums">{index + 1}</span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-medium text-ink">{mistake.concept}</p>
            <p className="text-sm text-graphite">
              {mistake.error_type === "wrong_option" ? "Çoktan seçmelide yanlış şık" : "Açık uçlu cevapta eksik"}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-4 text-sm">
            <span className="text-ink tabular-nums">
              <span className="font-semibold">{mistake.students}</span> öğrenci · {mistake.count} deneme
            </span>
            {mistake.fixing_source_ids[0] && (
              <button type="button" className="link" onClick={() => onOpenSource(mistake.fixing_source_ids[0])}>
                Konuyu anlatan bölüm
              </button>
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

function PracticeItemsSection({
  courseId,
  onOpenSource,
}: {
  courseId: number;
  onOpenSource: (id: string) => void;
}) {
  const toast = useToast();
  const { data, setData, failed, reload } = useLoad(
    (signal) => instructorService.practiceItems(courseId, signal),
    [courseId],
  );
  const [target, setTarget] = useState<ReviewTarget | null>(null);
  const [approving, setApproving] = useState<number | null>(null);

  function applyReview(itemId: number, decision: "approve" | "correct", correction: string | null, createdAt: string) {
    setData((items) =>
      (items ?? []).map((item) =>
        item.id === itemId
          ? {
              ...item,
              status: decision === "approve" ? "released" : "withdrawn",
              rubric_approved: decision === "approve",
              latest_review: { decision, correction, created_at: createdAt },
            }
          : item,
      ),
    );
  }

  async function approve(item: PracticeItemReview) {
    setApproving(item.id);
    try {
      const review = await instructorService.review({ target_type: "practice_item", target_id: item.id, decision: "approve" });
      applyReview(item.id, "approve", null, review.created_at);
      toast.show({ tone: "success", title: "Soru onaylandı", description: "Öğrencilere sunulmaya devam ediyor." });
    } catch {
      toast.show({ tone: "danger", title: "Onay kaydedilemedi", description: "Bağlantını kontrol edip tekrar dene." });
    } finally {
      setApproving(null);
    }
  }

  return (
    <section>
      <SectionHeader
        title="Pratik soruları"
        description="Sistemin ders materyalinden ürettiği ve otomatik kontrollerden geçen son sorular. Hatalı olanı düzelt; öğrencilere artık sunulmaz."
      />
      {failed ? (
        <LoadFailed what="Pratik soruları" onRetry={reload} />
      ) : !data ? (
        <SkeletonRows rows={3} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={ListChecks}
          title="Henüz pratik sorusu yok"
          description={'Öğrenciler AI Tutor\'da "beni test et" dedikçe üretilen sorular burada incelenir.'}
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {data.map((item) => (
            <PracticeItemCard
              key={item.id}
              item={item}
              approving={approving === item.id}
              onApprove={() => void approve(item)}
              onCorrect={() => setTarget({ type: "practice_item", id: item.id, summary: item.prompt })}
              onOpenSource={onOpenSource}
            />
          ))}
        </ul>
      )}
      <ReviewDialog
        target={target}
        onClose={() => setTarget(null)}
        onSaved={(review) => {
          applyReview(review.target_id, "correct", review.correction, review.created_at);
          setTarget(null);
          toast.show({ tone: "success", title: "Düzeltme kaydedildi", description: "Soru öğrencilere artık sunulmuyor." });
        }}
      />
    </section>
  );
}

function PracticeItemCard({
  item,
  approving,
  onApprove,
  onCorrect,
  onOpenSource,
}: {
  item: PracticeItemReview;
  approving: boolean;
  onApprove: () => void;
  onCorrect: () => void;
  onOpenSource: (id: string) => void;
}) {
  const withdrawn = item.status === "withdrawn";
  return (
    <li className="rounded-panel border border-line bg-surface p-4 shadow-card">
      <div className="flex flex-wrap items-center gap-2 text-sm text-graphite">
        <Badge>{TYPE_LABELS[item.type]}</Badge>
        <Badge>{DIFFICULTY_LABELS[item.difficulty]}</Badge>
        {item.topic && <span className="truncate">{item.topic}</span>}
        <span className="ml-auto text-xs">{formatRelative(item.created_at)}</span>
      </div>
      <p className="mt-3 text-base whitespace-pre-wrap text-ink">{item.prompt}</p>
      {item.options && (
        <ol className="mt-3 flex flex-col gap-1.5">
          {item.options.map((option, index) => (
            <li
              key={index}
              className={
                index === item.correct_option
                  ? "rounded-control border border-success/40 bg-success-soft px-3 py-1.5 text-base text-ink"
                  : "rounded-control border border-line px-3 py-1.5 text-base text-ink-2"
              }
            >
              <span className="mr-2 font-semibold">{"ABCDEF"[index]})</span>
              {option}
              {index === item.correct_option && <span className="sr-only"> (doğru cevap)</span>}
            </li>
          ))}
        </ol>
      )}
      {item.reference_answer && (
        <p className="mt-3 text-base text-ink-2">
          <span className="font-medium text-ink">Referans cevap: </span>
          {item.reference_answer}
        </p>
      )}
      <details className="mt-3">
        <summary className="cursor-pointer text-sm text-graphite hover:text-ink">Açıklama</summary>
        <p className="mt-2 text-base whitespace-pre-wrap text-ink-2">{item.explanation}</p>
      </details>

      <div className="mt-4 flex flex-col gap-3 border-t border-line pt-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1 text-sm">
          {withdrawn ? (
            <p className="flex items-start gap-1.5 text-warning">
              <TriangleAlert size={14} aria-hidden className="mt-0.5 shrink-0" />
              <span>
                Düzeltildi, öğrencilere sunulmuyor.
                {item.latest_review?.correction && <span className="text-ink-2"> “{item.latest_review.correction}”</span>}
              </span>
            </p>
          ) : item.rubric_approved ? (
            <p className="flex items-center gap-1.5 text-success">
              <CircleCheck size={14} aria-hidden />
              Onaylandı
            </p>
          ) : (
            <p className="text-graphite">Henüz incelenmedi</p>
          )}
          <button type="button" className="link mt-1" onClick={() => onOpenSource(item.source.source_id)}>
            Dayandığı yer: {citationLabel(item.source)}
          </button>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button size="sm" onClick={onCorrect}>
            Düzelt
          </Button>
          <Button size="sm" variant="primary" icon={CircleCheck} loading={approving} onClick={onApprove}>
            {withdrawn ? "Yeniden onayla" : "Onayla"}
          </Button>
        </div>
      </div>
    </li>
  );
}
