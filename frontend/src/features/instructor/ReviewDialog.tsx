import { useState, type FormEvent } from "react";

import type { ReviewDecision, ReviewOut } from "../../api/types";
import { instructorService } from "../../services/instructorService";
import Button from "../../ui/Button";
import Dialog from "../../ui/Dialog";
import ErrorText from "../../ui/ErrorText";
import { inputClasses } from "../../ui/Field";
import { cx } from "../../ui/cx";

const MAX_CORRECTION = 4000;

/** Çok satırlı alan: metin kutusuyla aynı görünüm, yüksekliği satır sayısından. */
const textareaClasses = cx(inputClasses.replace(/(^|\s)h-10(?=\s|$)/, "$1").trim(), "py-2 leading-relaxed");

export interface ReviewTarget {
  type: ReviewDecision["target_type"];
  id: number;
  /** Diyalogda hatırlatma olarak gösterilen metin (soru ya da öğrencinin sorusu). */
  summary: string;
}

/**
 * Eğitmenin bir asistan cevabını ya da pratik sorusunu düzeltmesi (#20, #22).
 * Düzeltme metni zorunludur; pratik sorusu düzeltilince öğrencilere artık sunulmaz.
 */
export default function ReviewDialog({
  target,
  onClose,
  onSaved,
}: {
  target: ReviewTarget | null;
  onClose: () => void;
  onSaved: (review: ReviewOut) => void;
}) {
  const [correction, setCorrection] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function close() {
    if (saving) return;
    setCorrection("");
    setError(null);
    onClose();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!target) return;
    if (!correction.trim()) {
      setError("Neyin yanlış olduğunu ve doğrusunu yaz.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const review = await instructorService.review({
        target_type: target.type,
        target_id: target.id,
        decision: "correct",
        correction: correction.trim(),
      });
      setCorrection("");
      onSaved(review);
    } catch {
      setError("Düzeltme kaydedilemedi. Bağlantını kontrol edip tekrar dene.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={target !== null}
      onClose={close}
      size="lg"
      title={target?.type === "practice_item" ? "Pratik sorusunu düzelt" : "Asistanın cevabını düzelt"}
      description={
        target?.type === "practice_item"
          ? "Düzeltilen soru öğrencilere artık sunulmaz. Sonra yeniden onaylayabilirsin."
          : "Düzeltmen kaydedilir; asistanın hatalarını izlemek ve materyali iyileştirmek için kullanılır."
      }
      footer={
        <>
          <Button variant="ghost" onClick={close} disabled={saving}>
            Vazgeç
          </Button>
          <Button variant="primary" type="submit" form="review-form" loading={saving}>
            Düzeltmeyi kaydet
          </Button>
        </>
      }
    >
      <form id="review-form" onSubmit={(event) => void submit(event)} className="flex flex-col gap-3">
        {target && (
          <blockquote className="border-l-2 border-line-strong pl-3 text-base text-ink-2">{target.summary}</blockquote>
        )}
        <label className="flex flex-col gap-1.5">
          <span className="text-sm font-medium text-ink-2">Düzeltme</span>
          <textarea
            value={correction}
            onChange={(event) => setCorrection(event.target.value)}
            maxLength={MAX_CORRECTION}
            rows={5}
            aria-required="true"
            data-autofocus
            aria-invalid={error ? true : undefined}
            placeholder="Ne yanlış, doğrusu ne? Gerekirse ders materyalindeki yeri de yaz."
            className={textareaClasses}
          />
        </label>
        {error && <ErrorText>{error}</ErrorText>}
      </form>
    </Dialog>
  );
}
