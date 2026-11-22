import { useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";

import { ApiError } from "../../api/client";
import { userMessage } from "../../api/errors";
import { useDemoInfo } from "../../auth/useDemoInfo";
import { courseService } from "../../services/courseService";
import Button from "../../ui/Button";
import ErrorText from "../../ui/ErrorText";
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
  const errorId = useId();

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
          : userMessage(reason, "Derse katılamadın. Tekrar dene."),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <form onSubmit={submit} className="flex flex-col gap-2" noValidate>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Field
            label="Katılım kodu"
            placeholder="Eğitmenin verdiği kod"
            value={code}
            onChange={(event) => {
              setCode(event.target.value);
              if (error) setError(null);
            }}
            aria-invalid={error ? true : undefined}
            aria-describedby={error ? errorId : undefined}
            autoComplete="off"
            className="sm:w-72"
          />
          <Button type="submit" variant="primary" loading={saving} disabled={!code.trim()}>
            Derse katıl
          </Button>
        </div>
        {error && (
          <div id={errorId}>
            <ErrorText>{error}</ErrorText>
          </div>
        )}
      </form>
      {demoCodes.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm text-graphite">
          <span className="mr-1">Demo kodları:</span>
          {demoCodes.map((c) => (
            <Button
              key={c.course_id}
              variant="ghost"
              size="sm"
              onClick={() => {
                setCode(c.join_code);
                setError(null);
              }}
              title={c.name}
            >
              {c.code}
              <code className="font-mono font-normal text-graphite">{c.join_code}</code>
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
