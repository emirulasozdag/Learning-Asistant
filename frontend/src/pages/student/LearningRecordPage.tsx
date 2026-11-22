import { BarChart3, CircleCheck, ServerOff, Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import type { AttemptSummary, ConceptProgress, LearningRecord } from "../../api/types";
import { useCourseOutlet } from "../../features/courses/courseOutlet";
import { formatScore } from "../../features/practice/labels";
import { SourceDrawer } from "../../features/tutor/SourceViewer";
import { citationLabel } from "../../labels";
import { learningService } from "../../services/learningService";
import { formatRelative } from "../../text";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import { buttonClasses } from "../../ui/buttonStyles";
import Card from "../../ui/Card";
import { cx } from "../../ui/cx";
import EmptyState from "../../ui/EmptyState";
import Notice from "../../ui/Notice";
import { SectionHeader } from "../../ui/PageHeader";
import PageTitle from "../../ui/PageTitle";
import { SkeletonRows } from "../../ui/Skeleton";

const TYPE_LABELS: Record<AttemptSummary["type"], string> = {
  mcq: "Çoktan seçmeli",
  short_answer: "Kısa cevap",
  code_tracing: "Kod izleme",
};

/** Öğrencinin bu dersteki kendi öğrenme kaydı (#20, #22): pratik denemeleri ve kavramlar. */
export default function LearningRecordPage() {
  const { course } = useCourseOutlet();
  const [record, setRecord] = useState<LearningRecord | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [sourceId, setSourceId] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    learningService
      .record(course.id, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setRecord(data);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [course.id, attempt]);

  const practicePath = `/student/courses/${course.id}/practice`;

  return (
    <div>
      <PageTitle
        title="Öğrenme kaydım"
        description="Pratik sayfasında ve AI Tutor'da çözdüğün sorulardan hesaplanır. Puanlar çalışman içindir, resmî not değildir."
      />
      {failed ? (
        <EmptyState
          icon={ServerOff}
          tone="danger"
          title="Öğrenme kaydı yüklenemedi"
          description="Kayda şu an ulaşılamıyor. Bağlantını kontrol edip tekrar dene."
          action={
            <Button
              onClick={() => {
                setFailed(false);
                setRecord(null);
                setAttempt((value) => value + 1);
              }}
            >
              Tekrar dene
            </Button>
          }
        />
      ) : !record ? (
        <SkeletonRows rows={4} />
      ) : (
        <div className="flex flex-col gap-10">
          {!record.logging_enabled && <LoggingOffNotice hasAttempts={record.attempts.length > 0} />}
          {record.attempts.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="Henüz kayıtlı deneme yok"
              description={
                record.logging_enabled
                  ? "Pratik sayfasında ya da AI Tutor'da soru çöz; hangi kavramlarda iyi olduğun ve neleri tekrar etmen gerektiği burada görünür."
                  : "Öğrenme kaydı kapalıyken çözdüğün sorular buraya yazılmaz."
              }
              action={
                <Link to={practicePath} className={buttonClasses("primary")}>
                  Pratik yap
                </Link>
              }
            />
          ) : (
            <>
              <section>
                <SectionHeader
                  title="Kavramlar"
                  description="Önce hâlâ eksiği olan kavramlar. Kaynağa tıklayıp konuyu ders materyalinden tekrar et."
                />
                <ul className="grid gap-4 md:grid-cols-2">
                  {record.concepts.map((concept) => (
                    <ConceptCard key={concept.concept} concept={concept} onOpenSource={setSourceId} />
                  ))}
                </ul>
              </section>
              <section>
                <SectionHeader title="Denemelerim" description="En yeni deneme önce." />
                <AttemptList attempts={record.attempts} />
              </section>
            </>
          )}
        </div>
      )}
      {sourceId && <SourceDrawer sourceId={sourceId} onClose={() => setSourceId(null)} />}
    </div>
  );
}

function LoggingOffNotice({ hasAttempts }: { hasAttempts: boolean }) {
  return (
    <Notice
      tone="info"
      role="note"
      action={
        <Link to="/student/account" className={buttonClasses("secondary", "sm")}>
          <Settings size={14} aria-hidden />
          Ayarı değiştir
        </Link>
      }
    >
      Öğrenme kaydın şu an <strong className="font-semibold text-ink">kapalı</strong>. Çözdüğün sorulara yine
      geri bildirim alırsın ama yeni denemeler bu sayfaya yazılmaz.
      {hasAttempts && " Aşağıda kayıt açıkken yaptığın denemeler görünüyor."}
    </Notice>
  );
}

function percent(ratio: number): string {
  return `%${Math.round(ratio * 100)}`;
}

function ConceptCard({ concept, onOpenSource }: { concept: ConceptProgress; onOpenSource: (id: string) => void }) {
  const done = concept.open_gaps.length === 0;
  return (
    <Card as="li" className="flex flex-col gap-3">
      <div className="flex items-start gap-3">
        <p className="min-w-0 flex-1 text-md font-semibold text-ink">{concept.concept}</p>
        {done ? (
          <Badge tone="success">
            <CircleCheck size={12} aria-hidden />
            Son deneme tam
          </Badge>
        ) : (
          <Badge tone="warning">Tekrar et</Badge>
        )}
      </div>
      <div>
        <div className="h-1.5 overflow-hidden rounded-full bg-subtle" aria-hidden>
          <span
            className={cx("block h-full rounded-full", done ? "bg-success" : "bg-warning")}
            style={{ width: `${Math.max(4, concept.last_score_ratio * 100)}%` }}
          />
        </div>
        <p className="mt-1.5 text-sm text-graphite">
          Son puan <span className="font-semibold text-ink tabular-nums">{percent(concept.last_score_ratio)}</span>
          {" · "}en iyi <span className="tabular-nums">{percent(concept.best_score_ratio)}</span>
          {" · "}
          {concept.attempts} deneme
        </p>
      </div>
      {!done && (
        <div>
          <p className="text-sm font-semibold text-graphite">Eksik görünenler</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {concept.open_gaps.map((gap) => (
              <li key={gap}>
                <Badge>{gap}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {concept.source && (
        <button
          type="button"
          onClick={() => onOpenSource(concept.source!.source_id)}
          className="link self-start text-sm"
        >
          Kaynağı aç: {citationLabel(concept.source)}
        </button>
      )}
    </Card>
  );
}

function AttemptList({ attempts }: { attempts: AttemptSummary[] }) {
  return (
    <ul className="flex flex-col divide-y divide-line border-y border-line">
      {attempts.map((attempt) => {
        const full = attempt.max_score > 0 && attempt.score >= attempt.max_score;
        return (
          <li key={attempt.attempt_id} className="flex items-start gap-4 py-3">
            <div className="min-w-0 flex-1">
              <p className="text-base text-ink">{attempt.concept ?? "Genel"}</p>
              <p className="mt-0.5 text-sm text-graphite">
                {TYPE_LABELS[attempt.type]}
                {attempt.missing_concepts.length > 0 && ` · eksik: ${attempt.missing_concepts.join(", ")}`}
              </p>
              {attempt.withdrawn && (
                <p className="mt-1 text-sm text-warning">Bu soru eğitmen tarafından düzeltildi ve geri çekildi.</p>
              )}
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <Badge tone={full ? "success" : attempt.score > 0 ? "warning" : "danger"}>
                {formatScore(attempt.score)} / {formatScore(attempt.max_score)}
              </Badge>
              <span className="text-xs text-graphite tabular-nums">{formatRelative(attempt.attempted_at)}</span>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
