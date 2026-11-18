import { CircleCheck, CircleX } from "lucide-react";
import { forwardRef } from "react";

import type { AnswerFeedback } from "../../api/types";
import { cx } from "../../ui/cx";
import RichText from "../tutor/RichText";
import { conceptLabel, formatScore, resultOf } from "./labels";

/**
 * Cevabın formatif geri bildirimi: sonuç ve puan, açıklama, kavradıkların / eksiklerin, rubrik
 * ölçütleri ve örnek tam puanlık cevap. Sabit örnek geri bildirim yoktur; hepsi API'den gelir.
 * Kök eleman odaklanabilir (`tabIndex=-1`): gönderimden sonra odak buraya taşınabilir.
 */
const PracticeFeedback = forwardRef<HTMLDivElement, { feedback: AnswerFeedback }>(function PracticeFeedback(
  { feedback },
  ref,
) {
  const result = resultOf(feedback.score, feedback.max_score);
  const Icon = result.tone === "success" ? CircleCheck : CircleX;
  return (
    <div ref={ref} tabIndex={-1} role="status" className="flex flex-col gap-3 outline-none">
      <p className="flex items-center gap-2 text-base font-medium text-ink">
        <Icon
          size={16}
          aria-hidden
          className={cx(
            result.tone === "success" ? "text-success" : result.tone === "danger" ? "text-danger" : "text-warning",
          )}
        />
        {result.label}
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
});

export default PracticeFeedback;

function ConceptList({ title, items, tone }: { title: string; items: string[]; tone: "success" | "warning" }) {
  return (
    <div className={cx("rounded-panel px-3 py-2", tone === "success" ? "bg-success-soft" : "bg-warning-soft")}>
      <p className={cx("mb-1 text-sm font-medium", tone === "success" ? "text-success" : "text-warning")}>{title}</p>
      <ul className="list-disc pl-5 text-base text-ink">
        {items.map((concept) => (
          <li key={concept}>
            <RichText text={conceptLabel(concept)} inline />
          </li>
        ))}
      </ul>
    </div>
  );
}
