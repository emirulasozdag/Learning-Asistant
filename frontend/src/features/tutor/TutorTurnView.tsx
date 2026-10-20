import { CircleAlert, Hand, HelpCircle, Info, Lightbulb, ShieldAlert } from "lucide-react";

import type { ClarificationBlock, GeneralExplanationBlock, NoticeBlock, NoticeKind } from "../../api/types";
import type { QuickAction } from "../../services/tutorService";
import Button from "../../ui/Button";
import AnswerBlock from "./AnswerBlock";
import PracticeChain from "./PracticeCard";
import RichText from "./RichText";
import { extraSegments } from "./turns";
import type { Segment, SelectSourceProps, TutorTurn } from "./types";

interface TurnExtrasProps extends SelectSourceProps {
  turn: TutorTurn;
  isLatest: boolean;
  /** Turda gösterilen (ya da beklenen) bir kaynaklı cevap var mı; yoksa bekleme satırı burada. */
  hasAnswer: boolean;
  onQuickAction: (action: QuickAction) => void;
  onRetry: () => void;
  /** Netleştirme seçeneği gibi bir yanıtı yeni mesaj olarak gönderir. */
  onAsk: (text: string) => void;
}

/**
 * Turun kaynaklı cevap dışındaki blokları (ADR-7): pratik sorusu, her zaman etiketli genel bilgi,
 * netleştirme sorusu, sabit bilgilendirme ve (çok parçalı soruda) ikinci kaynaklı cevap. Ayrıca
 * araç çalışırken gerçek adımı gösteren bekleme satırı. `follow_ups` çizilmez: cevabın altındaki
 * hızlı eylemler aynı işi görür.
 */
export default function TurnExtras({
  turn,
  isLatest,
  hasAnswer,
  onQuickAction,
  onRetry,
  onAsk,
  selectedSourceId,
  onSelectSource,
}: TurnExtrasProps) {
  const select = { selectedSourceId, onSelectSource };
  const extras = extraSegments(turn);
  const running = !turn.done && !turn.failure && !turn.stopped;
  const lastDone = extras.length === 0 || extras[extras.length - 1].block !== undefined;
  // Kaynaklı cevap kendi bekleme durumunu gösterir; burada yalnızca başka araçlar için.
  const showPending = running && lastDone && (turn.status !== undefined || (!hasAnswer && extras.length === 0));

  if (extras.length === 0 && !showPending) return null;
  return (
    <div className="flex flex-col gap-5">
      {extras.map((segment, index) => (
        <Extra
          key={index}
          segment={segment}
          turn={turn}
          isLatest={isLatest}
          onQuickAction={onQuickAction}
          onRetry={onRetry}
          onAsk={onAsk}
          {...select}
        />
      ))}
      {showPending && <Pending label={turn.status ?? "Mesajın inceleniyor"} />}
    </div>
  );
}

function Extra({
  segment,
  turn,
  isLatest,
  onQuickAction,
  onRetry,
  onAsk,
  ...select
}: SelectSourceProps & {
  segment: Segment;
  turn: TutorTurn;
  isLatest: boolean;
  onQuickAction: (action: QuickAction) => void;
  onRetry: () => void;
  onAsk: (text: string) => void;
}) {
  const { block } = segment;
  if (block?.type === "course_answer" || (!block && segment.tool === "answer_from_course")) {
    return (
      <AnswerBlock
        turn={{
          id: `${turn.id}-extra`,
          question: turn.question,
          hits: segment.hits,
          streamText: segment.streamText,
          response: block?.type === "course_answer" ? block.response : undefined,
        }}
        isLatest={isLatest}
        onQuickAction={onQuickAction}
        onRetry={onRetry}
        {...select}
      />
    );
  }
  if (block?.type === "practice") return <PracticeChain item={block.item} {...select} />;
  if (block?.type === "general_explanation") return <GeneralExplanation block={block} />;
  if (block?.type === "clarification") return <Clarification block={block} disabled={!isLatest} onAsk={onAsk} />;
  if (block?.type === "notice") return <Notice block={block} />;
  if (!block && segment.tool === "explain_general" && !turn.stopped && !turn.failure) {
    return <GeneralDraft text={segment.streamText} />;
  }
  return null;
}

function GeneralExplanation({ block }: { block: GeneralExplanationBlock }) {
  return (
    <section aria-label="Genel bilgi" className="rounded-panel border border-line bg-surface px-4 py-4 shadow-card">
      <GeneralBadge />
      <div className="text-md leading-7 text-ink">
        <RichText text={block.text} />
      </div>
      <p className="mt-3 text-sm text-graphite">
        {block.notice}
        {block.check === "unchecked" && " Bu açıklama henüz otomatik doğrulamadan geçmedi."}
      </p>
    </section>
  );
}

function GeneralDraft({ text }: { text: string }) {
  if (!text) return <Pending label="Genel bilgi açıklaması hazırlanıyor" />;
  return (
    <section aria-busy="true" className="rounded-panel border border-line bg-surface px-4 py-4 shadow-card">
      <GeneralBadge />
      <div className="text-md leading-7 text-graphite opacity-80">
        <RichText text={text} />
        <span aria-hidden className="ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse bg-warning" />
      </div>
    </section>
  );
}

function GeneralBadge() {
  return (
    <p className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-warning-soft px-2.5 py-1 font-mono text-xs font-medium text-warning">
      <Lightbulb size={13} aria-hidden />
      Genel bilgi · ders materyalinden değil
    </p>
  );
}

function Clarification({
  block,
  disabled,
  onAsk,
}: {
  block: ClarificationBlock;
  disabled: boolean;
  onAsk: (text: string) => void;
}) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p className="flex items-start gap-2 text-md leading-7 text-ink">
        <HelpCircle size={16} aria-hidden className="mt-1.5 shrink-0 text-accent" />
        {block.question}
      </p>
      {block.options.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {block.options.map((option) => (
            <Button key={option} size="sm" disabled={disabled} onClick={() => onAsk(option)}>
              {option}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

const NOTICE_ICON: Record<NoticeKind, typeof Info> = {
  greeting: Hand,
  off_topic: Info,
  graded_work: ShieldAlert,
  not_covered: Info,
  unavailable: Info,
  failure: CircleAlert,
};

function Notice({ block }: { block: NoticeBlock }) {
  const Icon = NOTICE_ICON[block.kind];
  return (
    <p className="flex max-w-[46rem] items-start gap-2.5 rounded-panel border border-line bg-surface px-4 py-3 text-md leading-7 text-ink shadow-card">
      <Icon size={16} aria-hidden className="mt-1.5 shrink-0 text-graphite" />
      {block.text}
    </p>
  );
}

function Pending({ label }: { label: string }) {
  return (
    <p className="flex h-7 items-center gap-2 text-base text-graphite">
      {label.replace(/…$/, "")}
      <span aria-hidden className="flex gap-1">
        <span className="thinking-dot size-1 rounded-full bg-graphite" />
        <span className="thinking-dot size-1 rounded-full bg-graphite" />
        <span className="thinking-dot size-1 rounded-full bg-graphite" />
      </span>
    </p>
  );
}
