import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { useDemoInfo } from "../../auth/useDemoInfo";
import { courseService } from "../../services/courseService";
import Button from "../../ui/Button";
import Field from "../../ui/Field";
import { useToast } from "../../ui/toast/context";
import { useCourses } from "./context";

/** Eğitmenin verdiği katılım koduyla derse öğrenci olarak katılma (ADR-2). */
export default function JoinCourseForm() {
  const { add, courses } = useCourses();
  // Sunum modu: öğrencinin henüz katılmadığı derslerin kodları tek tıkla kutuya yazılır.
  const demo = useDemoInfo();
  const demoCodes = demo?.courses.filter((c) => !courses.some((course) => course.id === c.course_id)) ?? [];
  const toast = useToast();
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const course = await courseService.join(code.trim());
      add(course);
      setCode("");
      toast.show({ tone: "success", title: `${course.code} dersine katıldın` });
      navigate(`/student/courses/${course.id}`);
    } catch (reason) {
      setError(
        reason instanceof ApiError && reason.status === 404
          ? "Bu kodla bir ders bulunamadı. Kod yanlış ya da süresi dolmuş olabilir."
          : reason instanceof Error
            ? reason.message
            : String(reason),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-start" noValidate>
        <Field
          label="Katılım kodu"
          placeholder="Eğitmenin verdiği kod"
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
            if (error) setError(null);
          }}
          error={error}
          autoComplete="off"
          className="sm:w-72"
        />
        <Button type="submit" loading={saving} disabled={!code.trim()} className="sm:mt-[1.6rem]">
          Derse katıl
        </Button>
      </form>
      {demoCodes.length > 0 && (
        <p className="flex flex-wrap items-center gap-2 text-sm text-graphite">
          <span>Demo kodları:</span>
          {demoCodes.map((c) => (
            <button
              key={c.course_id}
              type="button"
              onClick={() => {
                setCode(c.join_code);
                setError(null);
              }}
              className="rounded-control border border-line bg-surface px-2 py-1 text-ink hover:border-line-strong hover:bg-canvas"
              title={c.name}
            >
              <span className="font-semibold">{c.code}</span>{" "}
              <code className="font-mono tracking-wider">{c.join_code}</code>
            </button>
          ))}
        </p>
      )}
    </div>
  );
}
