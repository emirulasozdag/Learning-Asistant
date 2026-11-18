import { ArrowRight, BookOpen, Flag, LoaderCircle, RotateCcw, SlidersHorizontal, Target } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import type { AnswerFeedback, AnswerSubmission } from "../../api/types";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import { cx } from "../../ui/cx";
import { classifyFailure } from "../tutor/outcome";
import RichText from "../tutor/RichText";
import SourceCards from "../tutor/SourceCards";
import { AnswerText, ChoiceList } from "./AnswerInput";
import { DIFFICULTY_LABEL, TYPE_LABEL, formatScore, resultOf, type ResultTone } from "./labels";
import PracticeFeedback from "./PracticeFeedback";
import type { PracticeEntry, PracticeSession } from "./usePracticeSession";

const TONE_DOT: Record<ResultTone, string> = {
  success: "bg-success border-success",
  warning: "bg-warning border-warning",
  danger: "bg-danger border-danger",
};

/**
 * Süren oturum: üstte konu ve ilerleme, ortada tek soru. Önceki sorular altta, kapalı bir
 * listede tekrar okunabilir. Soru hazırlanırken ya da hazırlanamadığında soru kartının yerini
 * dürüst bir durum kartı alır.
 */
export default function PracticeSessionView({
  session,
  selectedSourceId,
  onSelectSource,
}: {
  session: PracticeSession;
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}) {
  const { entries, generating, failure, settings } = session;
  const current = generating || failure ? null : entries[entries.length - 1] ?? null;
  const previous = current ? entries.slice(0, -1) : entries;

  return (
    <div className="flex flex-col gap-6">
      <SessionBar session={session} />

      {generating ? (
        <GeneratingCard topic={settings?.topic} onCancel={session.cancel} />
      ) : failure ? (
        <div role="alert" className="rounded-panel border border-danger/30 bg-danger-soft px-5 py-4">
          <p className="text-base font-medium text-ink">{failure.detail}</p>
          {failure.kind === "no_item" && (
            <p className="mt-1 text-sm text-graphite">
              Konuyu farklı kelimelerle yazmayı ya da başka bir soru türü seçmeyi dene.
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {failure.kind !== "rejected" && (
              <Button size="sm" icon={RotateCcw} onClick={session.retry}>
                Tekrar dene
              </Button>
            )}
            <Button size="sm" variant="ghost" icon={SlidersHorizontal} onClick={session.openSetup}>
              Konuyu ya da türü değiştir
            </Button>
          </div>
        </div>
      ) : current ? (
        <QuestionCard
          key={current.item.id}
          entry={current}
          number={entries.length}
          session={session}
          selectedSourceId={selectedSourceId}
          onSelectSource={onSelectSource}
        />
      ) : null}

      {previous.length > 0 && <PreviousQuestions entries={previous} />}
    </div>
  );
}

function SessionBar({ session }: { session: PracticeSession }) {
  const { entries, generating, settings } = session;
  const answered = entries.filter((entry) => entry.feedback);
  const correct = answered.filter((entry) => entry.feedback!.score >= entry.feedback!.max_score).length;
  return (
    // Geniş ekranda kaydırırken üstte kalır; telefonda yer kaplamasın diye akışta durur.
    <div className="z-10 flex flex-wrap items-center gap-x-5 gap-y-3 rounded-panel border border-line bg-surface/95 px-4 py-3 shadow-card backdrop-blur sm:sticky sm:top-0">
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium tracking-wide text-graphite uppercase">Konu</p>
        <p className="truncate text-md font-semibold text-ink">{settings?.topic ?? "Pratik"}</p>
        {settings && (
          <p className="mt-0.5 flex flex-wrap gap-1.5">
            <Badge>{TYPE_LABEL[settings.type]}</Badge>
            <Badge>{DIFFICULTY_LABEL[settings.difficulty]}</Badge>
          </p>
        )}
      </div>

      <div className="flex flex-col items-start gap-1">
        <ol aria-label="Oturum ilerlemesi" className="flex flex-wrap items-center gap-1">
          {entries.map((entry, index) => {
            const result = entry.feedback ? resultOf(entry.feedback.score, entry.feedback.max_score) : null;
            return (
              <li
                key={entry.item.id}
                className={cx(
                  "size-2.5 rounded-full border",
                  result ? TONE_DOT[result.tone] : "border-accent bg-surface",
                )}
              >
                <span className="sr-only">
                  Soru {index + 1}: {result ? result.label : "cevaplanmadı"}
                </span>
              </li>
            );
          })}
          {generating && (
            <li aria-hidden className="size-2.5 animate-pulse rounded-full border border-line-strong bg-subtle" />
          )}
        </ol>
        <p className="text-sm text-graphite tabular-nums">
          {answered.length} cevap · {correct} doğru
        </p>
      </div>

      <div className="flex gap-1.5">
        <Button size="sm" variant="ghost" icon={SlidersHorizontal} onClick={session.openSetup}>
          Ayarlar
        </Button>
        <Button size="sm" icon={Flag} onClick={session.finish} disabled={entries.length === 0}>
          Oturumu bitir
        </Button>
      </div>
    </div>
  );
}

function GeneratingCard({ topic, onCancel }: { topic?: string; onCancel: () => void }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-panel border border-line bg-surface px-5 py-6 shadow-card"
    >
      <p className="flex items-center gap-2 text-base font-medium text-ink">
        <LoaderCircle size={16} aria-hidden className="animate-spin text-accent" />
        Soru hazırlanıyor
      </p>
      <p className="mt-1 text-sm text-graphite">
        {topic ? `"${topic}" için` : "Konu için"} ders materyalinden bir bölüm seçiliyor, soru yazılıyor ve
        bağımsız bir çözümle kontrol ediliyor. Bu genellikle 5–15 saniye sürer.
      </p>
      <div aria-hidden className="mt-5 flex flex-col gap-2.5">
        <span className="h-4 w-4/5 animate-pulse rounded bg-subtle" />
        <span className="h-4 w-3/5 animate-pulse rounded bg-subtle" />
        {[0, 1, 2, 3].map((index) => (
          <span key={index} className="h-10 w-full animate-pulse rounded-panel bg-subtle/70" />
        ))}
      </div>
      <Button size="sm" variant="ghost" className="mt-4" onClick={onCancel}>
        Vazgeç
      </Button>
    </div>
  );
}

/** Klavyeyle yazılan bir alanda mı (kısayollar orada devre dışı)? */
function isTyping(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return Boolean(target.closest("textarea, select, [contenteditable='true'], input:not([type='radio'])"));
}

/** Enter'ın kendi işi olan öğeler (düğme, bağlantı, açılır başlık). */
function isActivatable(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && Boolean(target.closest("button, a, summary"));
}

function QuestionCard({
  entry,
  number,
  session,
  selectedSourceId,
  onSelectSource,
}: {
  entry: PracticeEntry;
  number: number;
  session: PracticeSession;
  selectedSourceId: string | null;
  onSelectSource: (sourceId: string) => void;
}) {
  const { item } = entry;
  const mcq = item.type === "mcq";
  const [selected, setSelected] = useState<number | null>(entry.answer?.selected_option ?? null);
  const [text, setText] = useState(entry.answer?.answer_text ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const feedback: AnswerFeedback | null = entry.feedback;
  const headingRef = useRef<HTMLHeadingElement>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const name = useId();
  const hintId = useId();
  const canSubmit = !feedback && !submitting && (mcq ? selected !== null : text.trim().length > 0);
  const optionCount = item.options?.length ?? 0;
  const followUp =
    feedback !== null && feedback.score < feedback.max_score && feedback.missing_concepts.length > 0;

  // Yeni soru gelince odak soru başlığına: klavye ve ekran okuyucu kullanıcısı soruyu hemen okur.
  useEffect(() => {
    if (!entry.feedback) headingRef.current?.focus();
    // Yalnızca soru ilk göründüğünde.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const body: AnswerSubmission = mcq ? { selected_option: selected } : { answer_text: text.trim() };
    try {
      await session.answer(item.id, body);
      // Gönder düğmesi kaybolur; odak geri bildirime taşınır.
      requestAnimationFrame(() => feedbackRef.current?.focus());
    } catch (reason) {
      const failure = classifyFailure(reason);
      setError(failure.detail || "Cevap şu an değerlendirilemedi. Biraz sonra tekrar dene.");
    } finally {
      setSubmitting(false);
    }
  }

  // Kısayollar: 1–4 / A–D şık seçer, Enter gönderir; geri bildirimden sonra N sıradaki soru.
  const submitRef = useRef(submit);
  useEffect(() => {
    submitRef.current = submit;
  });
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      if (isTyping(event.target) || document.querySelector("[role='dialog']")) return;
      const key = event.key.toLocaleLowerCase("tr");
      if (!feedback) {
        if (mcq) {
          const index = /^[1-4]$/.test(key) ? Number(key) - 1 : /^[a-d]$/.test(key) ? key.charCodeAt(0) - 97 : -1;
          if (index >= 0 && index < optionCount) {
            event.preventDefault();
            setSelected(index);
            return;
          }
        }
        if (event.key === "Enter" && !isActivatable(event.target)) {
          event.preventDefault();
          void submitRef.current();
        }
      } else if (key === "n") {
        event.preventDefault();
        session.nextQuestion();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [feedback, mcq, optionCount, session]);

  return (
    <section
      aria-labelledby={`${name}-title`}
      className="rounded-panel border border-line bg-surface px-5 py-5 shadow-card sm:px-6"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2
          ref={headingRef}
          id={`${name}-title`}
          tabIndex={-1}
          className="text-sm font-semibold tracking-wide text-accent uppercase outline-none focus-visible:underline"
        >
          Soru {number}
        </h2>
        <Badge>{TYPE_LABEL[item.type]}</Badge>
        <Badge>{DIFFICULTY_LABEL[item.difficulty]}</Badge>
      </div>

      <div className="mt-3 text-lg leading-8 text-ink">
        <RichText text={item.prompt} />
      </div>

      <div className="mt-5">
        {mcq ? (
          <ChoiceList
            name={name}
            options={item.options ?? []}
            selected={selected}
            onSelect={setSelected}
            feedback={feedback}
            disabled={!!feedback || submitting}
            shortcuts
          />
        ) : (
          <AnswerText
            type={item.type}
            value={text}
            onChange={setText}
            disabled={!!feedback || submitting}
            onSubmitShortcut={() => void submit()}
            describedBy={hintId}
          />
        )}
      </div>

      {!feedback ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
          <Button variant="primary" loading={submitting} disabled={!canSubmit} onClick={() => void submit()}>
            {submitting ? "Değerlendiriliyor" : "Cevabı gönder"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={BookOpen}
            onClick={() => onSelectSource(item.source.source_id)}
          >
            Takıldın mı? Dayandığı bölümü aç
          </Button>
          <p id={hintId} className="hidden text-xs text-faint sm:block">
            {mcq ? "1–4 ya da A–D ile seç, Enter ile gönder" : "⌘/Ctrl + Enter ile gönder"}
          </p>
        </div>
      ) : null}

      {error && (
        <p role="alert" className="mt-3 text-sm text-danger">
          {error}
        </p>
      )}

      {feedback && (
        <>
          <div className="mt-5 border-t border-line pt-5">
            <PracticeFeedback ref={feedbackRef} feedback={feedback} />
          </div>

          <div className="mt-5">
            <p className="mb-2 text-sm font-medium text-ink-2">Cevabını kaynakla karşılaştır</p>
            <SourceCards
              citations={[item.source]}
              numbered={false}
              selectedSourceId={selectedSourceId}
              onSelectSource={onSelectSource}
            />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-5">
            <Button variant="primary" trailingIcon={ArrowRight} onClick={session.nextQuestion}>
              Sonraki soru
            </Button>
            {followUp && (
              <Button icon={Target} onClick={() => session.followUp(entry)}>
                Eksiklerim üzerine soru
              </Button>
            )}
            <Button variant="ghost" icon={Flag} onClick={session.finish}>
              Oturumu bitir
            </Button>
            <span className="hidden text-xs text-faint sm:inline">N ile sonraki soru</span>
          </div>
        </>
      )}
    </section>
  );
}

function PreviousQuestions({ entries }: { entries: PracticeEntry[] }) {
  return (
    <details className="rounded-panel border border-line bg-surface px-4 py-3">
      <summary className="cursor-pointer text-sm font-medium text-ink-2 select-none">
        Bu oturumdaki önceki sorular ({entries.length})
      </summary>
      <ol className="mt-3 flex flex-col divide-y divide-line">
        {entries.map((entry, index) => (
          <li key={entry.item.id} className="py-2.5">
            <EntryRow entry={entry} number={index + 1} />
          </li>
        ))}
      </ol>
    </details>
  );
}

/** Oturum listesindeki bir soru: sonuç, puan ve sorunun ilk satırı. */
export function EntryRow({ entry, number }: { entry: PracticeEntry; number: number }) {
  const result = entry.feedback ? resultOf(entry.feedback.score, entry.feedback.max_score) : null;
  return (
    <div className="flex items-start gap-3">
      <span
        aria-hidden
        className={cx(
          "mt-1.5 size-2.5 shrink-0 rounded-full border",
          result ? TONE_DOT[result.tone] : "border-line-strong bg-surface",
        )}
      />
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 text-base text-ink">
          <span className="font-medium text-graphite">{number}. </span>
          <RichText text={entry.item.prompt.split("\n")[0]} inline />
        </p>
        <p className="text-sm text-graphite">
          {TYPE_LABEL[entry.item.type]} ·{" "}
          {result && entry.feedback
            ? `${result.label} · ${formatScore(entry.feedback.score)}/${formatScore(entry.feedback.max_score)} puan`
            : "Cevaplanmadı"}
        </p>
      </div>
    </div>
  );
}
