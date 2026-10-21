import { CircleCheck, CircleX, ClipboardCheck, Repeat, Target } from "lucide-react";
import { useId, useState } from "react";

import { api } from "../../api/client";
import type { AnswerFeedback, PracticeItem, PracticeType } from "../../api/types";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import { classifyFailure } from "./outcome";
import RichText from "./RichText";
import SourceCards from "./SourceCards";
import type { SelectSourceProps } from "./types";

const TYPE_LABEL: Record<PracticeType, string> = {
  mcq: "Çoktan seçmeli",
  short_answer: "Kısa cevap",
  code_tracing: "Kod izleme",
};

const DIFFICULTY_LABEL = { easy: "Kolay", medium: "Orta", hard: "Zor" } as const;

/**
 * Pratik zinciri: tutor'un ürettiği soru, öğrencinin cevabı ve geri bildirim. Geri bildirimden
 * sonra "eksiklerim üzerine" ya da "benzer" yeni soru aynı zincire eklenir (CONTRACTS.md §2).
 * Cevap anahtarı ve referans cevap yalnızca cevap gönderildikten sonra gelir.
 */
export default function PracticeChain({ item, ...select }: SelectSourceProps & { item: PracticeItem }) {
  const [items, setItems] = useState<PracticeItem[]>([item]);
  return (
    <div className="flex flex-col gap-4">
      {items.map((current, index) => (
        <PracticeCard
          key={current.id}
          item={current}
          isLast={index === items.length - 1}
          onNext={(next) => setItems((list) => [...list, next])}
          {...select}
        />
      ))}
    </div>
  );
}

function PracticeCard({
  item,
  isLast,
  onNext,
  ...select
}: SelectSourceProps & { item: PracticeItem; isLast: boolean; onNext: (item: PracticeItem) => void }) {
  const [selected, setSelected] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<AnswerFeedback | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nextLoading, setNextLoading] = useState<"follow_up" | "similar" | null>(null);
  const name = useId();
  const mcq = item.type === "mcq";
  const canSubmit = !feedback && !submitting && (mcq ? selected !== null : text.trim().length > 0);

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      setFeedback(
        await api.submitAnswer(item.id, mcq ? { selected_option: selected } : { answer_text: text.trim() }),
      );
    } catch (reason) {
      const failure = classifyFailure(reason);
      setError(failure.detail || "Cevap şu an değerlendirilemedi. Biraz sonra tekrar dene.");
    } finally {
      setSubmitting(false);
    }
  }

  async function next(kind: "follow_up" | "similar") {
    if (!feedback) return;
    setNextLoading(kind);
    setError(null);
    try {
      onNext(
        await api.generatePractice({
          course_id: item.course_id,
          type: item.type,
          difficulty: item.difficulty,
          ...(kind === "follow_up"
            ? { follow_up_of_attempt_id: feedback.attempt_id }
            : { source_id: item.source.source_id }),
        }),
      );
    } catch (reason) {
      const failure = classifyFailure(reason);
      setError(failure.detail || "Yeni soru şu an hazırlanamadı.");
    } finally {
      setNextLoading(null);
    }
  }

  return (
    <section
      aria-label="Pratik sorusu"
      className="rounded-panel border border-line bg-surface px-4 py-4 shadow-card"
    >
      <div className="mb-3 flex flex-wrap items-center gap-1.5">
        <span className="mr-1 flex items-center gap-1.5 text-sm font-medium text-ink-2">
          <ClipboardCheck size={14} aria-hidden className="text-accent" />
          Pratik sorusu
        </span>
        <Badge>{TYPE_LABEL[item.type]}</Badge>
        <Badge>{DIFFICULTY_LABEL[item.difficulty]}</Badge>
        {item.topic && <Badge tone="accent">{item.topic}</Badge>}
      </div>

      <div className="text-md leading-7 text-ink">
        <RichText text={item.prompt} />
      </div>

      {mcq ? (
        <fieldset className="mt-4 flex flex-col gap-2" disabled={!!feedback || submitting}>
          <legend className="sr-only">Seçenekler</legend>
          {(item.options ?? []).map((option, index) => {
            const correct = feedback?.correct_option === index;
            const chosenWrong = feedback && selected === index && !correct;
            return (
              <label
                key={index}
                className={cx(
                  "flex cursor-pointer items-start gap-3 rounded-panel border px-3 py-2 text-base",
                  correct
                    ? "border-success bg-success-soft"
                    : chosenWrong
                      ? "border-danger bg-danger-soft"
                      : selected === index
                        ? "border-accent bg-accent-soft/60"
                        : "border-line hover:border-line-strong",
                  feedback && "cursor-default",
                )}
              >
                <input
                  type="radio"
                  name={name}
                  className="mt-1 accent-[var(--color-accent)]"
                  checked={selected === index}
                  onChange={() => setSelected(index)}
                />
                <span className="font-medium text-graphite">{"ABCD"[index]})</span>
                <span className="text-ink">
                  <RichText text={option} inline />
                </span>
              </label>
            );
          })}
        </fieldset>
      ) : (
        <label className="mt-4 block">
          <span className="sr-only">Cevabın</span>
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={!!feedback || submitting}
            rows={item.type === "code_tracing" ? 5 : 4}
            placeholder={item.type === "code_tracing" ? "Çıktıyı ya da adımları yaz" : "Cevabını yaz"}
            className={cx(
              "w-full rounded-panel border border-line bg-surface px-3 py-2 text-base text-ink",
              "focus:border-accent focus:outline-none disabled:bg-canvas",
              item.type === "code_tracing" && "font-mono text-sm",
            )}
          />
        </label>
      )}

      {!feedback && (
        <div className="mt-3 flex items-center gap-3">
          <Button variant="primary" size="sm" loading={submitting} disabled={!canSubmit} onClick={() => void submit()}>
            {submitting ? "Değerlendiriliyor" : "Cevabı gönder"}
          </Button>
          <p className="text-sm text-graphite">Puan formatiftir; resmî not değildir.</p>
        </div>
      )}

      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}

      {feedback && <Feedback feedback={feedback} />}

      <div className="mt-4">
        <p className="mb-2 text-sm text-graphite">Sorunun dayandığı bölüm</p>
        <SourceCards citations={[item.source]} numbered={false} {...select} />
      </div>

      {feedback && isLast && (
        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          {feedback.score < feedback.max_score && feedback.missing_concepts.length > 0 && (
            <Button
              size="sm"
              icon={Target}
              loading={nextLoading === "follow_up"}
              disabled={nextLoading !== null}
              onClick={() => void next("follow_up")}
            >
              Eksiklerim üzerine yeni soru
            </Button>
          )}
          <Button
            size="sm"
            icon={Repeat}
            loading={nextLoading === "similar"}
            disabled={nextLoading !== null}
            onClick={() => void next("similar")}
          >
            Benzer bir soru daha
          </Button>
          {nextLoading && (
            <span role="status" className="text-sm text-graphite">
              Soru hazırlanıyor ve bağımsız çözümle kontrol ediliyor; bu birkaç saniye sürebilir.
            </span>
          )}
        </div>
      )}
    </section>
  );
}

function Feedback({ feedback }: { feedback: AnswerFeedback }) {
  const full = feedback.score >= feedback.max_score;
  const none = feedback.score === 0;
  return (
    <div role="status" className="mt-4 flex flex-col gap-3 border-t border-line pt-4">
      <p className="flex items-center gap-2 text-base font-medium text-ink">
        {full ? (
          <CircleCheck size={16} aria-hidden className="text-success" />
        ) : (
          <CircleX size={16} aria-hidden className={none ? "text-danger" : "text-warning"} />
        )}
        {full ? "Doğru" : none ? "Doğru değil" : "Kısmen doğru"}
        <span className="text-graphite">
          · {formatScore(feedback.score)} / {formatScore(feedback.max_score)} puan
        </span>
      </p>

      <div className="text-md leading-7 text-ink">
        <RichText text={feedback.explanation} />
      </div>

      {(feedback.understood.length > 0 || feedback.missing_concepts.length > 0) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {feedback.understood.length > 0 && (
            <ConceptList title="Kavradıkların" items={feedback.understood} tone="success" />
          )}
          {feedback.missing_concepts.length > 0 && (
            <ConceptList title="Eksik ya da yanlış" items={feedback.missing_concepts} tone="warning" />
          )}
        </div>
      )}

      {feedback.criteria.length > 0 && (
        <details className="text-sm text-graphite">
          <summary className="cursor-pointer select-none">Rubrik ölçütleri</summary>
          <ul className="mt-2 flex flex-col gap-1.5">
            {feedback.criteria.map((criterion, index) => (
              <li key={index}>
                <span className="font-medium text-ink-2">
                  {formatScore(criterion.awarded)}/{formatScore(criterion.points)}
                </span>{" "}
                {criterion.description}
                {criterion.rationale && (
                  <span className="block text-faint">
                    <RichText text={criterion.rationale} inline />
                  </span>
                )}
              </li>
            ))}
          </ul>
        </details>
      )}

      {feedback.reference_answer && (
        <details className="text-sm">
          <summary className="cursor-pointer text-graphite select-none">Örnek tam puanlık cevap</summary>
          <div className="mt-2 text-base text-ink">
            <RichText text={feedback.reference_answer} />
          </div>
        </details>
      )}
    </div>
  );
}

function ConceptList({ title, items, tone }: { title: string; items: string[]; tone: "success" | "warning" }) {
  return (
    <div className={cx("rounded-panel px-3 py-2", tone === "success" ? "bg-success-soft" : "bg-warning-soft")}>
      <p className={cx("mb-1 text-sm font-medium", tone === "success" ? "text-success" : "text-warning")}>{title}</p>
      <ul className="list-disc pl-5 text-base text-ink">
        {items.map((concept) => (
          <li key={concept}>
            <RichText text={concept.replace(/_/g, " ")} inline />
          </li>
        ))}
      </ul>
    </div>
  );
}

function formatScore(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(".", ",");
}
