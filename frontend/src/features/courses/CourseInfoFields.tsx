import { LEVEL_LABELS } from "../../labels";
import Field, { inputClasses } from "../../ui/Field";
import { cx } from "../../ui/cx";
import type { CourseInfoDraft } from "./courseInfoDraft";

/** Dersin tanıtım bilgileri: eğitmen, dönem, seviye, bölüm, açıklama (hepsi isteğe bağlı). */
export default function CourseInfoFields({
  draft,
  onChange,
}: {
  draft: CourseInfoDraft;
  onChange: (draft: CourseInfoDraft) => void;
}) {
  const set = (key: keyof CourseInfoDraft) => (value: string) => onChange({ ...draft, [key]: value });
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          label="Eğitmen"
          value={draft.instructor_name}
          onChange={(event) => set("instructor_name")(event.target.value)}
          maxLength={200}
        />
        <Field
          label="Bölüm"
          value={draft.department}
          onChange={(event) => set("department")(event.target.value)}
          placeholder="Bilgisayar Mühendisliği"
          maxLength={200}
        />
        <Field
          label="Dönem"
          value={draft.term}
          onChange={(event) => set("term")(event.target.value)}
          placeholder="Güz 2026"
          maxLength={64}
        />
        <div>
          <label htmlFor="course-level" className="mb-1.5 block text-sm font-medium text-ink-2">
            Seviye
          </label>
          <select
            id="course-level"
            value={draft.level}
            onChange={(event) => set("level")(event.target.value)}
            className={cx(inputClasses, "appearance-auto")}
          >
            <option value="">Belirtilmedi</option>
            {Object.entries(LEVEL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <label htmlFor="course-description" className="mb-1.5 block text-sm font-medium text-ink-2">
          Ders açıklaması
        </label>
        <textarea
          id="course-description"
          value={draft.description}
          onChange={(event) => set("description")(event.target.value)}
          rows={4}
          maxLength={4000}
          placeholder="Dersin kapsamı, ön koşulları ve öğrencilerin kazanacakları."
          className={cx(inputClasses, "h-auto py-2 leading-relaxed")}
        />
      </div>
    </div>
  );
}
