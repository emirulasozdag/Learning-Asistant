import { CircleCheck, MessageSquareText, ServerOff } from "lucide-react";
import { useEffect, useState } from "react";
import { useParams } from "react-router";

import type { CourseActivity, QuestionItem } from "../../api/types";
import ReviewDialog, { type ReviewTarget } from "../../features/instructor/ReviewDialog";
import { pageLabel } from "../../labels";
import { instructorService } from "../../services/instructorService";
import { formatDay, formatRelative } from "../../text";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import EmptyState from "../../ui/EmptyState";
import { SectionHeader } from "../../ui/PageHeader";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";
import StatRow from "../../ui/StatRow";
import { cx } from "../../ui/cx";
import { useToast } from "../../ui/toast/context";

/** Dersin soru-cevap etkinliği: tamamı kayıtlı mesajlardan; öğrenci kimliği içermez. */
export default function CourseActivityPage() {
  return (
    <div>
      <PageTitle
        title="Etkinlik ve analitik"
        description="Öğrencilerin AI Tutor'a sorduğu sorulardan hesaplanır; öğrenci kimliği tutulmaz."
      />
      <ActivityBody />
    </div>
  );
}

function ActivityBody() {
  const courseId = Number(useParams().courseId);
  const [activity, setActivity] = useState<CourseActivity | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    instructorService
      .activity(courseId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setActivity(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [courseId, attempt]);

  function reload() {
    setFailed(false);
    setActivity(null);
    setAttempt((value) => value + 1);
  }

  if (failed) {
    return (
      <EmptyState
        icon={ServerOff}
        tone="danger"
        title="Etkinlik yüklenemedi"
        description="Ders etkinliğine şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
        action={<Button onClick={reload}>Tekrar dene</Button>}
      />
    );
  }
  if (!activity) return <SkeletonRows rows={4} />;
  if (activity.questions === 0) {
    // Sıfır "hiç soru yok" demek değildir: analitik yalnızca araştırma kaydını açan öğrencilerden
    // ve en az üç kişi olunca hesaplanır (ADR-4). Kaç kişinin sorduğu söylenmez (#105).
    return (
      <EmptyState
        icon={MessageSquareText}
        title="Gösterilecek etkinlik yok"
        description="Etkinlik yalnızca araştırma kaydını açan öğrencilerin sorularından ve en az üç farklı öğrenci soru sorduğunda gösterilir; böylece kimse tek başına ayırt edilemez. Öğrenciler soru sordukça sayılar, sık kullanılan kaynaklar ve materyalde bulunamayan sorular burada görünür."
      />
    );
  }

  const rate = (count: number) => `%${Math.round((count / activity.questions) * 100)}`;
  return (
    <div className="flex flex-col gap-12">
      <section>
        <StatRow
          stats={[
            { label: "Soru", value: activity.questions },
            { label: "Sohbet", value: activity.conversations },
            { label: "Kaynaklı cevap", value: activity.answered, hint: rate(activity.answered) },
            { label: "Materyalde yok", value: activity.not_covered, hint: rate(activity.not_covered) },
          ]}
        />
        <OutcomeBar activity={activity} />
      </section>

      <div className="grid gap-12 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <section>
          <SectionHeader title="Son 14 günde sorular" />
          <DailyChart daily={activity.daily} />
        </section>
        <section>
          <SectionHeader
            title="En çok alıntılanan sayfalar"
            description="Cevaplarda en sık dayanak olan ders sayfaları."
          />
          <TopSources sources={activity.top_sources} />
        </section>
      </div>

      <ReviewableQuestions activity={activity} />
    </div>
  );
}

/**
 * Soru listeleri: her sorunun yanında asistanın cevabını onaylama ya da düzeltme (#20, #22).
 * Sunucudaki son karar (`latest_review`) gösterilir; bu oturumda verilen karar onun yerine geçer.
 */
function ReviewableQuestions({ activity }: { activity: CourseActivity }) {
  const toast = useToast();
  const [target, setTarget] = useState<ReviewTarget | null>(null);
  const [decisions, setDecisions] = useState<Record<number, "approve" | "correct">>({});
  const [approving, setApproving] = useState<number | null>(null);

  async function approve(messageId: number) {
    setApproving(messageId);
    try {
      await instructorService.review({ target_type: "message", target_id: messageId, decision: "approve" });
      setDecisions((current) => ({ ...current, [messageId]: "approve" }));
      toast.show({ tone: "success", title: "Cevap onaylandı" });
    } catch {
      toast.show({ tone: "danger", title: "Onay kaydedilemedi", description: "Bağlantını kontrol edip tekrar dene." });
    } finally {
      setApproving(null);
    }
  }

  const review: ReviewControls = {
    decisions,
    approving,
    onApprove: (messageId) => void approve(messageId),
    onCorrect: (item) =>
      item.answer_message_id != null &&
      setTarget({ type: "message", id: item.answer_message_id, summary: item.question }),
  };

  return (
    <div className="grid gap-12 xl:grid-cols-2">
      <section>
        <SectionHeader
          title="Materyalde bulunamayan sorular"
          description="Bu konular için materyal eklemek öğrencilere cevap verilmesini sağlar."
        />
        <QuestionList items={activity.unanswered_questions} empty="Cevapsız kalan soru yok." review={review} />
      </section>
      <section>
        <SectionHeader title="Son sorular" description="Asistanın cevabını onayla ya da hatalıysa düzelt." />
        <QuestionList items={activity.recent_questions} empty="Henüz soru yok." review={review} />
      </section>
      <ReviewDialog
        target={target}
        onClose={() => setTarget(null)}
        onSaved={(saved) => {
          setDecisions((current) => ({ ...current, [saved.target_id]: "correct" }));
          setTarget(null);
          toast.show({ tone: "success", title: "Düzeltme kaydedildi" });
        }}
      />
    </div>
  );
}

interface ReviewControls {
  decisions: Record<number, "approve" | "correct">;
  approving: number | null;
  onApprove: (messageId: number) => void;
  onCorrect: (item: QuestionItem) => void;
}

const OUTCOME_PARTS = [
  { key: "answered", label: "Kaynaklı cevap", swatch: "bg-success" },
  { key: "not_covered", label: "Materyalde yok", swatch: "bg-line-strong" },
  { key: "not_generated", label: "Doğrulanamadı", swatch: "bg-warning" },
  { key: "unavailable", label: "Servis yanıt vermedi", swatch: "bg-danger" },
] as const;

/** Soruların sonuçlara dağılımı: tek yatay çubuk, renkler her zaman etiketle birlikte. */
function OutcomeBar({ activity }: { activity: CourseActivity }) {
  const parts = OUTCOME_PARTS.map((part) => ({ ...part, count: activity[part.key] })).filter((p) => p.count > 0);
  return (
    <div className="mt-8">
      <div className="flex h-2.5 gap-0.5 overflow-hidden rounded-full" aria-hidden>
        {parts.map((part) => (
          <span key={part.key} className={part.swatch} style={{ flexGrow: part.count }} />
        ))}
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-sm text-graphite">
        {parts.map((part) => (
          <li key={part.key} className="flex items-center gap-2">
            <span aria-hidden className={cx("size-2.5 rounded-sm", part.swatch)} />
            {part.label}
            <span className="font-semibold text-ink tabular-nums">{part.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}


/** Tek seri sütun grafiği: ince çubuklar, üzerine gelince değer; ekran okuyucu için tablo. */
function DailyChart({ daily }: { daily: CourseActivity["daily"] }) {
  const max = Math.max(1, ...daily.map((d) => d.questions));
  return (
    <figure>
      <div className="relative h-44 border-b border-line-strong">
        {[0.5, 1].map((line) => (
          <span
            key={line}
            aria-hidden
            className="absolute inset-x-0 border-t border-dashed border-line"
            style={{ bottom: `${line * 100}%` }}
          />
        ))}
        <span aria-hidden className="absolute -top-2.5 right-0 bg-canvas pl-2 text-xs text-faint tabular-nums">
          {max}
        </span>
        <div className="absolute inset-0 flex items-end gap-0.5 pr-8">
          {daily.map((day) => (
            <div key={day.day} className="group relative flex h-full flex-1 items-end justify-center">
              <span
                className={cx(
                  "w-full max-w-7 rounded-t-[4px] transition-colors",
                  day.questions > 0 ? "bg-accent group-hover:bg-accent-hover" : "bg-transparent",
                )}
                style={{ height: `${(day.questions / max) * 100}%` }}
              />
              <span className="pointer-events-none absolute bottom-full mb-1.5 hidden rounded-control bg-nav px-2 py-1 text-xs whitespace-nowrap text-white group-hover:block">
                {formatDay(day.day)}: {day.questions} soru
              </span>
            </div>
          ))}
        </div>
      </div>
      <div aria-hidden className="mt-2 flex justify-between pr-8 text-xs text-graphite">
        <span>{formatDay(daily[0].day)}</span>
        <span>Bugün</span>
      </div>
      <table className="sr-only">
        <caption>Son 14 günde günlük soru sayısı</caption>
        <tbody>
          {daily.map((day) => (
            <tr key={day.day}>
              <th scope="row">{formatDay(day.day)}</th>
              <td>{day.questions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}

function TopSources({ sources }: { sources: CourseActivity["top_sources"] }) {
  if (sources.length === 0) return <p className="text-base text-graphite">Henüz alıntı yok.</p>;
  const max = Math.max(...sources.map((s) => s.citations));
  return (
    <ol className="flex flex-col divide-y divide-line border-y border-line">
      {sources.map((source, index) => (
        <li key={source.source_id} className="flex items-center gap-4 py-3">
          <span className="w-4 text-sm font-semibold text-faint tabular-nums">{index + 1}</span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-medium text-ink">{source.document_title}</p>
            <div className="mt-1.5 flex items-center gap-3">
              <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle">
                <span
                  className="block h-full rounded-full bg-ink-2"
                  style={{ width: `${(source.citations / max) * 100}%` }}
                />
              </span>
            </div>
          </div>
          <div className="shrink-0 text-right text-sm whitespace-nowrap">
            <p className="font-semibold text-ink tabular-nums">{source.citations} alıntı</p>
            <p className="text-graphite">{source.page ? pageLabel(source.page) : "—"}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

const OUTCOME_BADGES: Record<string, { label: string; tone: "success" | "neutral" | "warning" | "danger" }> = {
  answered: { label: "Cevaplandı", tone: "success" },
  insufficient_evidence: { label: "Materyalde yok", tone: "neutral" },
  unsupported: { label: "Doğrulanamadı", tone: "warning" },
  model_refusal: { label: "Yanıtlanmadı", tone: "warning" },
  provider_failure: { label: "Servis yanıt vermedi", tone: "danger" },
  verification_failure: { label: "Kontrol edilemedi", tone: "danger" },
};

function QuestionList({ items, empty, review }: { items: QuestionItem[]; empty: string; review: ReviewControls }) {
  if (items.length === 0) return <p className="text-base text-graphite">{empty}</p>;
  return (
    <ul className="flex flex-col divide-y divide-line border-y border-line">
      {items.map((item, index) => {
        const badge = OUTCOME_BADGES[item.outcome] ?? OUTCOME_BADGES.answered;
        return (
          <li key={`${item.asked_at}-${index}`} className="flex items-start gap-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-base text-ink">{item.question}</p>
              {item.answer_message_id != null && (
                <ReviewActions messageId={item.answer_message_id} item={item} review={review} />
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge tone={badge.tone}>{badge.label}</Badge>
              <span className="text-xs text-graphite">{formatRelative(item.asked_at)}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function ReviewActions({ messageId, item, review }: { messageId: number; item: QuestionItem; review: ReviewControls }) {
  const decision = review.decisions[messageId] ?? item.latest_review?.decision;
  if (decision) {
    const correction = review.decisions[messageId] ? null : item.latest_review?.correction;
    return (
      <p className={cx("mt-1 flex items-start gap-1.5 text-sm", decision === "approve" ? "text-success" : "text-warning")}>
        <CircleCheck size={13} aria-hidden className="mt-0.5 shrink-0" />
        <span>
          {decision === "approve" ? "Cevabı onayladın" : "Düzeltmen kaydedildi"}
          {correction && <span className="text-ink-2"> “{correction}”</span>}
        </span>
      </p>
    );
  }
  return (
    <div className="mt-1.5 flex gap-3 text-sm">
      <button
        type="button"
        className="link disabled:opacity-50"
        disabled={review.approving === messageId}
        onClick={() => review.onApprove(messageId)}
        aria-label={`Cevabı onayla: ${item.question}`}
      >
        Onayla
      </button>
      <button
        type="button"
        className="link"
        onClick={() => review.onCorrect(item)}
        aria-label={`Cevabı düzelt: ${item.question}`}
      >
        Düzelt
      </button>
    </div>
  );
}
