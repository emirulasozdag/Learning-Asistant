import { ClipboardCheck, Repeat, Target } from "lucide-react";
import { useId, useState } from "react";

import { ApiError } from "../../api/client";
import type { AnswerFeedback, PracticeItem } from "../../api/types";
import { practiceService } from "../../services/practiceService";
import Badge from "../../ui/Badge";
import Button from "../../ui/Button";
import { AnswerText, ChoiceList } from "../practice/AnswerInput";
import { DIFFICULTY_LABEL, TYPE_LABEL } from "../practice/labels";
import PracticeFeedback from "../practice/PracticeFeedback";
import { classifyFailure } from "./outcome";
import RichText from "./RichText";
import SourceCards from "./SourceCards";
import type { SelectSourceProps } from "./types";

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
        await practiceService.answer(item.id, mcq ? { selected_option: selected } : { answer_text: text.trim() }),
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
        await practiceService.generate({
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
      // Yapay zekâya ulaşılamıyorsa backend'in açıklaması gösterilir (503, `ai_unavailable`).
      const unavailable = reason instanceof ApiError && reason.code === "ai_unavailable";
      setError((unavailable ? reason.message : failure.detail) || "Yeni soru şu an hazırlanamadı.");
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

      <div className="mt-4">
        {mcq ? (
          <ChoiceList
            name={name}
            options={item.options ?? []}
            selected={selected}
            onSelect={setSelected}
            feedback={feedback}
            disabled={!!feedback || submitting}
          />
        ) : (
          <AnswerText type={item.type} value={text} onChange={setText} disabled={!!feedback || submitting} />
        )}
      </div>

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

      {feedback && (
        <div className="mt-4 border-t border-line pt-4">
          <PracticeFeedback feedback={feedback} />
        </div>
      )}

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
